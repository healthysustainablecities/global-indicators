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
from sqlalchemy import text

# Danger-weighted accessibility (manuscript section 2.4).  Routing is over the rideable
# network **plus short dismount connectors** using the danger-weighted cost (cost_lts),
# which already encodes the per-link multipliers: LTS 1-2 = length + impedance, LTS 3-4 =
# length * danger_weight + impedance, and non-permitted links = length * dismount_weight
# (walk the bike).  Non-permitted links are only routable where ``dismount_routable`` (within
# a short dismount of the rideable network), bounding dismount to short connectors.  The
# primary binary indicator is "destination within the danger-weighted distance threshold"
# (sp_cycle_access_*); a strict "fully low-stress (rideable LTS <= 2) route exists" flag
# (sp_cycle_lowstress_access_*) is reported alongside for manuscript/R comparability, derived
# from the low-stress connected component of the origin and the destination access node.
CYCLE_COST = 'cost_lts'
CYCLE_REVERSE_COST = 'cost_lts_reverse'
ROUTABLE_WHERE = 'bike_permitted OR dismount_routable'
SAFE_WHERE = 'lvl_traf_stress <= 2 AND bike_permitted'
SAFE_COMP_TABLE = '_cycle_safe_comp'

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

# Activity-centre (destination cluster) defaults.  An activity centre is a network
# location whose pedestrian walk-shed (``walk_threshold`` m) contains at least one
# destination of every required ``category``.  Two tiers are derived by default,
# mapping a tier name to the destination ``variant`` it is built from: a "local"
# (everyday) centre from the lenient variants and a "complete" (high-amenity) centre
# from the strict variants.  Cycling safe-route access is then measured to the nearest
# centre of each tier, exactly like any other destination.  (INDICATOR_DESIGN.md §4.)
ACTIVITY_CENTRE_DEFAULTS = {
    'walk_threshold': 400,
    'categories': ['food', 'pos', 'pt'],
    'tiers': {'local': 'lenient', 'complete': 'strict'},
}

# Combined-access "all categories reachable" composites and activity centres are
# defined as named sets over a category list.  The 'standard' set keeps the bare,
# globally-comparable names (all_strict / all_lenient, activity_centre_<tier>); any
# other named set is namespaced (all_<set>_<variant>, activity_centre_<set>_<tier>).
STANDARD_SET = 'standard'
RESERVED_AC_KEYS = {'walk_threshold', 'categories', 'tiers'}


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


def _node_index(r):
    """Full ordered index of network node osmids."""
    return pd.Index(
        r.get_df('SELECT osmid FROM nodes ORDER BY osmid')['osmid'].to_numpy(
            dtype='int64',
        ),
        name='osmid',
    )


def _ensure_node_associations(r, layers):
    """Add nearest-node (n1/n2) associations to any layer lacking them."""
    for layer in sorted(layers):
        if 'n1' not in _table_columns(r, layer):
            r.add_nearest_node_associations(layer)


def _merge_ac_def(d):
    """Merge an activity-centre definition mapping over the built-in defaults."""
    out = dict(ACTIVITY_CENTRE_DEFAULTS)
    out['tiers'] = dict(ACTIVITY_CENTRE_DEFAULTS['tiers'])
    out.update({k: v for k, v in d.items() if v is not None})
    return out


def activity_centre_config(config):
    """Resolve the *standard* activity-centre options, or None if disabled.

    Enabled by default when cycling indicators are on; set ``activity_centres: false``
    to disable, or supply a mapping to override ``walk_threshold`` / ``categories`` /
    ``tiers``.
    """
    if not isinstance(config, dict):
        return None
    # enabled by default whenever cycling indicators are on (config is a mapping,
    # possibly empty); only an explicit false / null disables it
    ac = config.get('activity_centres', True)
    if ac is False or ac is None:
        return None
    cfg = dict(ACTIVITY_CENTRE_DEFAULTS)
    cfg['tiers'] = dict(ACTIVITY_CENTRE_DEFAULTS['tiers'])
    if isinstance(ac, dict):
        # only the standard option keys customise the standard definition; any
        # other keys are named definitions handled by activity_centre_definitions
        cfg.update(
            {k: v for k, v in ac.items() if v is not None and k in RESERVED_AC_KEYS},
        )
    return cfg


def activity_centre_definitions(config):
    """Resolve the activity-centre definitions as a {name: options} map, or {}.

    Backward compatible: ``true`` or a single-option mapping yields one 'standard'
    definition; a mapping of named definitions yields those, plus an implicit
    'standard' (unless the user defines their own).
    """
    standard = activity_centre_config(config)
    if standard is None:
        return {}
    defs = {STANDARD_SET: standard}
    ac = config.get('activity_centres', True)
    if isinstance(ac, dict) and not (RESERVED_AC_KEYS & set(ac)):
        # a mapping of named definitions (no top-level option keys)
        for name, d in ac.items():
            if isinstance(d, dict):
                defs[name] = _merge_ac_def(d)
    return defs


def _resolve_member(specs, category, variant):
    """Pick the spec for a category at a strictness variant, else its sole spec.

    Lets a single-variant custom category (e.g. a bike rack tagged ``any``) join
    both the strict and lenient combined indicators / activity-centre tiers.
    """
    cat_specs = [s for s in specs if s.get('category') == category]
    exact = [s for s in cat_specs if s.get('variant') == variant]
    if exact:
        return exact[0]
    if len(cat_specs) == 1:
        return cat_specs[0]
    return None


def combined_access_sets(config, specs):
    """Named 'all categories reachable' sets: ``set_name -> [categories]``.

    Always includes a 'standard' set over the global (strict/lenient) categories for
    cross-city comparability; the region ``combined_access`` config adds or overrides
    sets (e.g. a 'local_custom' set that also includes a locally-relevant category).
    """
    global_cats = sorted({
        s['category']
        for s in specs
        if s.get('category') and s.get('variant') in ('strict', 'lenient')
    })
    sets = {STANDARD_SET: global_cats}
    for name, spec in ((config or {}).get('combined_access') or {}).items():
        categories = (spec or {}).get('categories')
        if categories:
            sets[name] = list(categories)
    return sets


def _write_node_seed_layer(r, name, osmids):
    """Materialise a derived destination layer seeded directly at network nodes.

    The resulting table mimics a destination layer (n1/n2 + offsets) so it can be fed
    through the standard ``build_dest_node_lookup`` / ``_dist_from_lookup`` machinery:
    each centre node is its own seed with a zero offset.
    """
    with r.engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
    pd.DataFrame({'osmid': pd.Series(osmids, dtype='int64')}).to_sql(
        '_ac_seed', r.engine, if_exists='replace', index=False,
    )
    with r.engine.begin() as conn:
        conn.execute(text(
            f'CREATE TABLE "{name}" AS '
            f'SELECT n.osmid AS n1, NULL::bigint AS n2, '
            f'0.0::float AS n1_distance, NULL::float AS n2_distance, n.geom '
            f'FROM nodes n JOIN _ac_seed s ON n.osmid = s.osmid',
        ))
        conn.execute(text('DROP TABLE IF EXISTS _ac_seed'))


def derive_activity_centres(r, config, specs):
    """Derive activity-centre destination layers and return them as new specs.

    For each configured tier, identifies network nodes whose pedestrian walk-shed
    (``walk_threshold`` m) reaches at least one destination of every required category
    (the tier's ``variant`` of each), materialises those nodes as a destination layer,
    and returns a spec per non-empty tier so cycling access can be measured to them.
    """
    defs = activity_centre_definitions(config)
    if not defs:
        return []

    # plan each (definition, tier): the member spec per category at the tier's variant
    plans = []  # (def_name, tier, walk_threshold, [member specs])
    needed_layers = set()
    max_walk = 0.0
    for def_name, d in defs.items():
        categories = list(d['categories'])
        walk = d['walk_threshold']
        for tier, variant in d['tiers'].items():
            members = [_resolve_member(specs, c, variant) for c in categories]
            if not all(members):
                missing = [c for c, m in zip(categories, members) if m is None]
                print(
                    f"  - skipping activity centre '{def_name}/{tier}': no spec "
                    f'for {missing}',
                )
                continue
            plans.append((def_name, tier, walk, members))
            needed_layers.update(m['layer'] for m in members)
            max_walk = max(max_walk, float(walk))
    if not plans:
        return []

    node_index = _node_index(r)
    _ensure_node_associations(r, needed_layers)
    print('  Deriving activity centres (pedestrian walk-shed co-location)...')
    # one pedestrian walk-distance lookup over all needed layers, at the largest
    # configured walk threshold; each plan then thresholds down to its own walk
    build_dest_node_lookup(r, active_layers=needed_layers, distance=max_walk)
    new_specs = []
    for def_name, tier, walk, members in plans:
        walk_dist = pd.concat(
            [
                _dist_from_lookup(
                    r, m['layer'], m.get('where', ''), node_index,
                    f"_walk_{m['name']}",
                )
                for m in members
            ],
            axis=1,
        ).replace(-999, np.nan)
        anchors = node_index[(walk_dist <= walk).all(axis=1).to_numpy()]
        osmids = anchors.astype('int64').tolist()
        infix = '' if def_name == STANDARD_SET else f'{def_name}_'
        layer = f'activity_centre_{infix}{tier}'
        print(f'    {def_name}/{tier}: {len(osmids)} centre nodes')
        if not osmids:
            continue
        _write_node_seed_layer(r, layer, osmids)
        new_specs.append({
            'name': layer, 'category': 'activity_centre',
            'variant': f'{def_name}_{tier}', 'layer': layer,
        })
    drop_dest_node_lookup(r)
    return new_specs


def build_safe_components(r):
    """Label network nodes by connected component of the low-stress subgraph.

    Components are computed over the safe (LTS <= 2 AND bike_permitted) edge subgraph and
    written to ``_cycle_safe_comp(osmid, comp)``.  Two nodes share a component iff an
    all-LTS<=2 (fully low-stress) route connects them; a node touching no safe edge is
    absent (so no fully low-stress route can start or end there).
    """
    import networkx as nx

    safe = r.get_df(
        f'SELECT "from" AS u, "to" AS v FROM edges WHERE {SAFE_WHERE}',
    )
    g = nx.Graph()
    g.add_edges_from(zip(safe['u'].tolist(), safe['v'].tolist()))
    rows = [
        (int(osmid), comp_id)
        for comp_id, nodes in enumerate(nx.connected_components(g))
        for osmid in nodes
    ]
    df = pd.DataFrame(rows, columns=['osmid', 'comp'])
    df.to_sql(SAFE_COMP_TABLE, r.engine, if_exists='replace', index=False)
    with r.engine.begin() as conn:
        conn.execute(text(f'CREATE INDEX ON {SAFE_COMP_TABLE} (osmid)'))
    print(
        f'  Safe (LTS<=2) subgraph: {g.number_of_nodes()} nodes in '
        f'{df["comp"].nunique()} components',
    )
    return df


def _safe_dist_from_lookup(r, layer, where_clause, node_index, col_name):
    """Per-node distance to the nearest destination reachable by a fully low-stress route.

    Like ``setup_sp._dist_from_lookup`` but additionally requires the origin node and the
    destination's access node to share a low-stress connected component
    (``_cycle_safe_comp``), so a value is returned only where an all-LTS<=2 route exists.
    The distance carried is whatever cost the active lookup was built with (here the
    danger-weighted ``cost_lts``); the component test, not the distance, enforces the
    strict "fully low-stress" requirement.
    """
    default = pd.Series(-999.0, index=node_index, name=col_name)
    cond = f'WHERE {where_clause}' if where_clause else ''
    sql = (
        f'SELECT l.node::bigint AS osmid, MIN(l.dist + p.offset)::float AS dist '
        f'FROM _dest_node_lookup l '
        f'JOIN ('
        f'  SELECT n1::bigint AS start_vid, n1_distance::float AS offset '
        f'  FROM {layer} {cond} '
        f'  UNION ALL '
        f'  SELECT n2::bigint AS start_vid, n2_distance::float AS offset '
        f'  FROM {layer} {cond}'
        f') p ON l.start_vid = p.start_vid '
        f'JOIN {SAFE_COMP_TABLE} co ON co.osmid = l.node '
        f'JOIN {SAFE_COMP_TABLE} cd ON cd.osmid = l.start_vid '
        f'WHERE co.comp = cd.comp '
        f'GROUP BY l.node'
    )
    result = r.get_df(sql)
    if result is None or len(result) == 0:
        return default
    result = result.dropna(subset=['osmid'])
    if result.empty:
        return default
    result['osmid'] = result['osmid'].astype('int64')
    series = result.set_index('osmid')['dist'].astype(float)
    series.name = col_name
    default.update(series)
    return default


def cycling_poi_distance(r, distance, specs):
    """Per-node danger-weighted distance to the nearest destination, plus a strict flag.

    Routes the full bike-permitted network once on the **danger-weighted** cost
    (``cost_lts``), so higher-stress links are usable at a proportionate penalty.  From the
    single lookup it derives, per destination spec:

    * ``sp_cycle_nearest_node_<name>`` -- danger-weighted distance to the nearest
      destination over the full network (the primary, lenient indicator); and
    * ``sp_cycle_lowstress_nearest_node_<name>`` -- the same distance restricted to
      destinations sharing a low-stress (LTS <= 2) connected component with the origin, i.e.
      where a *fully low-stress* route exists (the strict manuscript/R indicator).
    """
    node_index = _node_index(r)
    # ensure each destination layer is associated with its nearest nodes (n1/n2)
    _ensure_node_associations(r, {s['layer'] for s in specs})
    build_safe_components(r)

    print('  Building cycling destination-node lookup '
          '(danger-weighted; rideable + dismount connectors)...')
    build_dest_node_lookup(
        r,
        active_layers={s['layer'] for s in specs},
        distance=distance,
        edge_table='edges',
        cost=CYCLE_COST,
        reverse_cost=CYCLE_REVERSE_COST,
        where=ROUTABLE_WHERE,
    )
    lenient = [
        _dist_from_lookup(
            r, s['layer'], s.get('where', ''), node_index,
            f"sp_cycle_nearest_node_{s['name']}",
        )
        for s in specs
    ]
    strict = [
        _safe_dist_from_lookup(
            r, s['layer'], s.get('where', ''), node_index,
            f"sp_cycle_lowstress_nearest_node_{s['name']}",
        )
        for s in specs
    ]
    drop_dest_node_lookup(r)
    nodes_poi_dist = pd.concat(lenient + strict, axis=1)
    # -999 marks nodes with no destination within the threshold -> missing
    nodes_poi_dist = (
        round(nodes_poi_dist, 0).replace(-999, np.nan).astype('Int64')
    )
    return nodes_poi_dist, node_index


def cycling_sample_point_access(
    r, nodes_poi_dist, node_index, thresholds, specs, config,
):
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

    # composite "all categories reachable" access, per named combined-access set and
    # strictness variant.  Each category contributes the spec matching the variant
    # (else its sole spec, so a single-variant custom category joins both).  The
    # 'standard' set keeps bare all_<variant> names for comparability; other sets are
    # namespaced all_<set>_<variant>.
    sets = combined_access_sets(config, specs)
    axis = [v for v in ('strict', 'lenient') if any(s.get('variant') == v for s in specs)]
    for set_name, categories in sets.items():
        for variant in axis:
            members = [
                m for m in (_resolve_member(specs, c, variant) for c in categories)
                if m is not None
            ]
            names = [m['name'] for m in members]
            if len(names) < 2:
                continue
            infix = '' if set_name == STANDARD_SET else f'{set_name}_'
            for threshold in thresholds:
                cols = [
                    f'sp_cycle_access_{n}_{threshold}m'
                    for n in names
                    if f'sp_cycle_access_{n}_{threshold}m' in sample_points.columns
                ]
                if len(cols) >= 2:
                    col = f'sp_cycle_access_all_{infix}{variant}_{threshold}m'
                    sample_points[col] = (
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
    # derive activity-centre (destination cluster) layers, then analyse them as
    # additional destinations alongside the configured specs
    specs = specs + derive_activity_centres(r, config, specs)
    nodes_poi_dist, node_index = cycling_poi_distance(r, max(thresholds), specs)
    sample_points = cycling_sample_point_access(
        r, nodes_poi_dist, node_index, thresholds, specs, config,
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
