"""
Cycling accessibility.

Optional GHSCI analysis step, gated by the region configuration flag
``cycling_indicators: true``.  Computes safe-route (LTS <= 2) cycling accessibility to
destinations by reusing the pgRouting destination-node lookup engine
(``setup_sp.build_dest_node_lookup`` / ``_dist_from_lookup``) over the cycling-cost
subgraph produced by ``_cycling_lts_network`` (run that first).

Routing is restricted to ``lvl_traf_stress <= 2 AND bike_permitted`` edges and uses the
directional LTS costs (``cost_lts`` / ``cost_lts_reverse``), so the reported distance is
the LTS-weighted "effective" safe-route distance (a few percent above true metres on
LTS 2 links; swap the cost columns for ``length`` if pure-metre distance is preferred).

A configurable list of destination "specs" is analysed (default: fresh food, public open
space and public transport, each in a stricter and a less-strict / pooled variant), plus
a composite "all categories" indicator per variant.  Writes, per sample point, to the
``sample_points_cycling`` table:
    sp_cycle_nearest_node_<name>      safe-route distance (m) to the nearest destination
    sp_cycle_access_<name>_<d>m       binary access within d metres (1 / 0)
    sp_cycle_access_all_<variant>_<d>m  composite: all categories of a variant reachable

To run independently:  python subprocesses/_cycling_accessibility.py <codename>
"""

import sys
import time

import ghsci
import numpy as np
import pandas as pd
from _cycling_lts_network import cycling_config
from script_running_log import script_running_log
from setup_sp import (
    _dist_from_lookup,
    binary_access_score,
    build_dest_node_lookup,
    create_full_nodes,
    drop_dest_node_lookup,
)

# Edge subgraph and costs for safe cycling routing (see _cycling_lts_network).
CYCLE_WHERE = 'lvl_traf_stress <= 2 AND bike_permitted'
CYCLE_COST = 'cost_lts'
CYCLE_REVERSE_COST = 'cost_lts_reverse'

# Default destination specs: each maps a GHSCI layer (optionally filtered by an SQL
# ``where``) to an indicator ``name``, tagged by ``category`` and strictness ``variant``
# so the composite "all categories" indicators can be derived per variant.
DEFAULT_DESTINATIONS = [
    {
        'name': 'fresh_food_market', 'category': 'food', 'variant': 'strict',
        'layer': 'destinations', 'where': "dest_name = 'fresh_food_market'",
    },
    {
        'name': 'fresh_food_pooled', 'category': 'food', 'variant': 'lenient',
        'layer': 'destinations',
        'where': "dest_name IN ('fresh_food_market', 'convenience')",
    },
    {
        'name': 'public_open_space_large', 'category': 'pos', 'variant': 'strict',
        'layer': 'aos_public_large_nodes_30m_line',
    },
    {
        'name': 'public_open_space_any', 'category': 'pos', 'variant': 'lenient',
        'layer': 'aos_public_any_nodes_30m_line',
    },
    {
        'name': 'pt_frequent', 'category': 'pt', 'variant': 'strict',
        'layer': 'pt_stops_headway', 'where': 'headway <= 20',
    },
    {
        'name': 'pt_any', 'category': 'pt', 'variant': 'lenient',
        'layer': 'destinations', 'where': "dest_name = 'pt_any'",
    },
]


def _table_columns(r, table):
    """Return the set of column names on a table."""
    sql = (
        'SELECT column_name FROM information_schema.columns '
        f"WHERE table_schema = 'public' AND table_name = '{table}'"
    )
    return set(r.get_df(sql)['column_name'])


def usable_destination_specs(r, specs):
    """Drop specs whose layer is not present in the database (e.g. no GTFS feed)."""
    available = set(r.get_tables())
    usable = []
    for s in specs:
        if s.get('layer') in available:
            usable.append(s)
        else:
            print(
                f"  - skipping destination '{s.get('name')}': layer "
                f"'{s.get('layer')}' not found",
            )
    return usable


def cycling_poi_distance(r, distance, specs):
    """Per-node safe-route distance to the nearest destination of each spec."""
    node_index = pd.Index(
        r.get_df('SELECT osmid FROM nodes ORDER BY osmid')['osmid'].to_numpy(
            dtype='int64',
        ),
        name='osmid',
    )
    # ensure each destination layer is associated with its nearest nodes (n1/n2)
    for layer in sorted({s['layer'] for s in specs}):
        if 'n1' not in _table_columns(r, layer):
            r.add_nearest_node_associations(layer)

    print('  Building cycling (LTS <= 2) destination-node lookup...')
    build_dest_node_lookup(
        r,
        active_layers={s['layer'] for s in specs},
        distance=distance,
        edge_table='edges',
        cost=CYCLE_COST,
        reverse_cost=CYCLE_REVERSE_COST,
        where=CYCLE_WHERE,
    )
    series = [
        _dist_from_lookup(
            r,
            s['layer'],
            s.get('where', ''),
            node_index,
            f"sp_cycle_nearest_node_{s['name']}",
        )
        for s in specs
    ]
    drop_dest_node_lookup(r)
    nodes_poi_dist = pd.concat(series, axis=1)
    # -999 marks nodes with no destination within the threshold -> missing
    nodes_poi_dist = (
        round(nodes_poi_dist, 0).replace(-999, np.nan).astype('Int64')
    )
    return nodes_poi_dist, node_index


def cycling_sample_point_access(r, nodes_poi_dist, node_index, thresholds, specs):
    """Map node distances to sample points; derive per-spec and composite access."""
    sample_points = r.get_gdf('urban_sample_points')
    sample_points.columns = [
        'geometry' if x == 'geom' else x for x in sample_points.columns
    ]
    sample_points = sample_points.set_index('point_id')

    # estimate each sample point's distance from its two terminal nodes + offsets;
    # no density statistics are needed for the cycling distance indicator
    nodes_simple = pd.DataFrame(index=node_index)
    full_nodes = create_full_nodes(
        sample_points, nodes_simple, nodes_poi_dist, [],
    )
    sample_points = sample_points[
        ['grid_id', 'edge_ogc_fid', 'geometry']
    ].join(full_nodes, how='left')

    distance_names = list(nodes_poi_dist.columns)
    for threshold in thresholds:
        access_names = [
            f"{x.replace('nearest_node', 'access')}_{threshold}m"
            for x in distance_names
        ]
        sample_points[access_names] = binary_access_score(
            sample_points, distance_names, threshold,
        )

    # composite access: all categories of a variant reachable within each threshold
    variants = {}
    for s in specs:
        if s.get('variant'):
            variants.setdefault(s['variant'], []).append(s['name'])
    for variant, names in variants.items():
        for threshold in thresholds:
            cols = [
                f'sp_cycle_access_{n}_{threshold}m'
                for n in names
                if f'sp_cycle_access_{n}_{threshold}m' in sample_points.columns
            ]
            if cols:
                sample_points[f'sp_cycle_access_all_{variant}_{threshold}m'] = (
                    sample_points[cols].fillna(0).astype(int).prod(axis=1)
                )
    return sample_points


def cycling_accessibility(codename):
    start = time.time()
    script = '_cycling_accessibility'
    task = 'Cycling safe-route accessibility for sample points'
    r = ghsci.Region(codename)
    config = cycling_config(r)
    if config is None:
        print(
            'cycling_indicators is not enabled for this region; '
            'skipping cycling accessibility.',
        )
        return
    if 'cost_lts' not in _table_columns(r, 'edges'):
        sys.exit(
            'edges has no cost_lts column; run _cycling_lts_network first.',
        )

    thresholds = tuple(config.get('distances') or (2000, 5000))
    specs = usable_destination_specs(
        r, config.get('destinations') or DEFAULT_DESTINATIONS,
    )
    if not specs:
        sys.exit('No cycling destination layers available to analyse.')

    print('\nCalculating cycling safe-route accessibility...')
    print(f"  Destinations: {', '.join(s['name'] for s in specs)}")
    nodes_poi_dist, node_index = cycling_poi_distance(r, max(thresholds), specs)
    sample_points = cycling_sample_point_access(
        r, nodes_poi_dist, node_index, thresholds, specs,
    )

    print('  Saving sample_points_cycling to database...')
    sample_points.columns = [
        'geom' if x == 'geometry' else x for x in sample_points.columns
    ]
    sample_points = sample_points.set_geometry('geom')
    with r.engine.connect() as connection:
        sample_points.to_postgis(
            'sample_points_cycling',
            connection,
            index=True,
            if_exists='replace',
        )
    access_cols = [
        c for c in sample_points.columns if c.startswith('sp_cycle_access_')
    ]
    reached = {c: int(sample_points[c].sum()) for c in access_cols}
    print(f'  Wrote sample_points_cycling ({len(sample_points)} points).')
    print(f'  Sample points with safe access: {reached}')
    script_running_log(r.config, script, task, start)
    r.engine.dispose()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    cycling_accessibility(codename)


if __name__ == '__main__':
    main()
