"""
Pedestrian accessibility (configurable destinations and distance bands).

Optional GHSCI analysis step, gated by the presence of an ``accessibility`` block in
the region configuration.  It brings the pedestrian analysis up to the flexibility
the cycling analysis already has: a region declares arbitrary destination "specs"
and activity-centre definitions once (see ``_accessibility_spec``), and this step
measures walking access to each of them, over the plain pedestrian network, at every
configured distance band.

This is deliberately *additional* to the standard pedestrian indicators computed by
``_11_neighbourhood_analysis`` from the fixed ``indicators.yml`` lists: those remain
the globally comparable core (``sp_nearest_node_<dest>`` capped at
``accessibility_distance``, ``sp_access_<dest>_score``) and are unchanged.  With no
``accessibility`` block configured, this step does nothing at all.

Writes to the ``sample_points_pedestrian`` table:

    sp_walk_nearest_node_<name>            distance (m) to the nearest destination
    sp_walk_access_<name>_<d>m             binary access within d metres (1 / 0)
    sp_walk_access_all_<variant>_<d>m      composite: all of a variant's categories
    sp_walk_count_<set>__<group>_<d>m      destinations of a sub-type within d metres
    sp_walk_diversity_<set>_<d>m           normalised Shannon entropy of those counts
    sp_walk_richness_<set>_<d>m            share of a set's sub-types reachable

Because the bands are configurable, the distance columns are censored at the
*largest* configured band rather than at 500 m, which is what makes a mean distance
to the nearest destination interpretable when aggregated by ``_12_aggregation``
(``avg_walk_dist_<name>`` / ``pop_avg_walk_dist_<name>``).

Configuration (all keys optional)::

    accessibility:
      pedestrian:
        distances: [500, 1000, 1500]   # bands; default: the network_analysis
                                       # accessibility_distance (500 m)
        routing_engine: pgrouting      # else the region's top-level setting
        workers: 4                     # pgRouting batch workers
      destinations: [...]              # else the built-in defaults
      activity_centres: {...}          # else the standard 400 m definition
      diversity: {...}                 # named sub-type sets; none by default

To run independently:  python subprocesses/_pedestrian_accessibility.py <codename>
"""

import sys
import time

import ghsci
from _accessibility_spec import (
    DEFAULT_DESTINATIONS,
    _banded_counts,
    _banded_distances,
    _build_dest_table,
    _build_origin_pool,
    _counts_inmemory,
    _ensure_node_associations,
    _nearest_distances_inmemory,
    accessibility_config,
    all_thresholds,
    derive_activity_centres,
    diversity_bands,
    diversity_sets,
    diversity_specs,
    drop_scratch_tables,
    effective_config,
    resolve_n_workers,
    sample_point_access,
    usable_destination_specs,
)
from script_running_log import script_running_log

# Column prefixes.  'sp_walk_' distinguishes these configurable, banded measures
# from the fixed indicators.yml columns ('sp_nearest_node_' / 'sp_access_'), which
# keep their names and their 500 m cap.
DISTANCE_PREFIX = 'sp_walk_nearest_node_'
ACCESS_PREFIX = 'sp_walk_access_'
# destinations configured with `direction: avoid` report the complement: the
# share living *beyond* the threshold, proximity being the harm
BEYOND_PREFIX = 'sp_walk_beyond_'
# diversity measures: how many destinations of each configured sub-type are
# reachable, and how evenly what is reachable is spread across those sub-types
COUNT_PREFIX = 'sp_walk_count_'
DIVERSITY_PREFIX = 'sp_walk_diversity_'
RICHNESS_PREFIX = 'sp_walk_richness_'
SAMPLE_POINT_TABLE = 'sample_points_pedestrian'

# The pedestrian network is the routable network as built; walking cost is plain
# edge length in both directions, with no subgraph restriction.
WALK_COST = 'length'


def pedestrian_config(r):
    """Resolve the pedestrian accessibility configuration, or None if not enabled.

    Enabled by the presence of an ``accessibility`` block.  The ``pedestrian``
    sub-block carries this analysis's own options (bands, engine, workers) and may
    also override any shared key; anything it does not set is inherited from the
    shared block.
    """
    shared = accessibility_config(r)
    if not shared:
        return None
    pedestrian = shared.get('pedestrian')
    if pedestrian is False:
        return None
    return effective_config(
        shared,
        pedestrian if isinstance(pedestrian, dict) else {},
    )


def resolve_thresholds(config):
    """Ascending, de-duplicated distance bands (metres).

    Defaults to the project's ``accessibility_distance`` so that an ``accessibility``
    block which only declares destinations still measures them at the standard 500 m.
    """
    distances = config.get('distances') or [
        ghsci.settings['network_analysis']['accessibility_distance'],
    ]
    return tuple(sorted({int(d) for d in distances}))


def pedestrian_poi_distance(
    r,
    thresholds,
    specs,
    n_workers=None,
    engine='pgrouting',
):
    """Origin-seeded nearest walking distance to each destination spec.

    Returns ``(nodes_poi_dist, node_index)``, indexed by origin (sample-point
    terminal) node with one ``sp_walk_nearest_node_<name>`` column per spec.  The
    pgRouting engine routes band by band over the ascending thresholds, re-routing
    only origins that have not yet reached every spec, so the outer bands touch only
    the few stragglers; the in-memory engine takes one exact Dijkstra pass per spec.
    """
    bands = sorted({int(t) for t in thresholds})
    _ensure_node_associations(r, {s['layer'] for s in specs})
    node_index = _build_origin_pool(r)
    _build_dest_table(r, specs)
    try:
        if engine == 'inmemory':
            print(
                f'  In-memory routing (exact, one Dijkstra pass per destination, '
                f'max distance {bands[-1]} m) over {len(node_index)} origins',
            )
            frame = _nearest_distances_inmemory(
                r,
                specs,
                bands[-1],
                node_index,
                WALK_COST,
                WALK_COST,
                None,
                DISTANCE_PREFIX,
            )
        else:
            print(
                f'  Banded routing ({len(bands)} bands: {bands}) over '
                f'{len(node_index)} origins',
            )
            frame = _banded_distances(
                r,
                specs,
                bands,
                node_index,
                WALK_COST,
                WALK_COST,
                None,
                DISTANCE_PREFIX,
                n_workers,
            )
    finally:
        drop_scratch_tables(r)
    return round(frame, 0).astype('Int64'), node_index


def pedestrian_counts(
    r,
    bands,
    specs,
    node_index,
    n_workers=None,
    engine='pgrouting',
):
    """Destinations of each diversity group reachable from each origin, per band.

    Counting is a separate pass from the nearest-distance routing because it
    needs a different traversal: the distance search may stop as soon as every
    destination has been found, whereas a count is only complete once the whole
    catchment has been explored.
    """
    if engine == 'inmemory':
        print(
            f'  In-memory counting over {len(specs)} destination sub-types, '
            f'bands {list(bands)} m',
        )
        return _counts_inmemory(
            r,
            specs,
            bands,
            node_index,
            WALK_COST,
            WALK_COST,
            None,
            COUNT_PREFIX,
        )
    print(
        f'  Banded counting over {len(specs)} destination sub-types, '
        f'bands {list(bands)} m',
    )
    return _banded_counts(
        r,
        specs,
        bands,
        node_index,
        WALK_COST,
        WALK_COST,
        None,
        COUNT_PREFIX,
        n_workers,
    )


def pedestrian_accessibility(codename):
    start = time.time()
    script = '_pedestrian_accessibility'
    task = 'Configurable pedestrian accessibility for sample points'
    r = ghsci.Region(codename)
    config = pedestrian_config(r)
    if config is None:
        print(
            'No accessibility configuration for this region; skipping the '
            'configurable pedestrian accessibility analysis.',
        )
        return

    thresholds = resolve_thresholds(config)
    specs = usable_destination_specs(
        r,
        config.get('destinations') or DEFAULT_DESTINATIONS,
    )
    if not specs:
        sys.exit('No pedestrian destination layers available to analyse.')

    # accessibility.pedestrian.routing_engine takes precedence; falls back to the
    # region's top-level routing_engine (shared with the standard analysis)
    engine = str(
        config.get('routing_engine')
        or r.config.get('routing_engine')
        or 'pgrouting',
    ).lower()
    if engine not in ('pgrouting', 'inmemory'):
        sys.exit(
            f"Unknown routing_engine '{engine}' "
            "(expected 'pgrouting' or 'inmemory').",
        )

    print(
        '\nCalculating pedestrian accessibility (configured destinations)...',
    )
    print(f"  Destinations: {', '.join(s['name'] for s in specs)}")
    print(f'  Distance bands: {list(thresholds)} m')
    # derive activity-centre (destination cluster) layers, then analyse them as
    # additional destinations alongside the configured specs.  Co-location is a
    # pedestrian property, so these are the same layers the cycling analysis uses;
    # whichever step runs second reuses them.
    n_workers = resolve_n_workers(config)
    specs = specs + derive_activity_centres(
        r,
        config,
        specs,
        n_workers=n_workers,
        engine=engine,
    )
    # a spec may set its own policy-relevant band (e.g. a petrol station judged
    # at 250 m); route far enough to resolve every band any spec asks for
    nodes_poi_dist, node_index = pedestrian_poi_distance(
        r,
        all_thresholds(specs, thresholds),
        specs,
        n_workers=n_workers,
        engine=engine,
    )
    # diversity sets, where configured: each group is counted within its bands,
    # then scored once the counts have been mapped onto the sample points
    sets = diversity_sets(config)
    nodes_counts = None
    if sets:
        group_specs = usable_destination_specs(r, diversity_specs(sets))
        if group_specs:
            _ensure_node_associations(r, {x['layer'] for x in group_specs})
            _build_dest_table(r, group_specs)
            try:
                nodes_counts = pedestrian_counts(
                    r,
                    diversity_bands(sets, thresholds),
                    group_specs,
                    node_index,
                    n_workers=n_workers,
                    engine=engine,
                )
            finally:
                drop_scratch_tables(r)

    sample_points = sample_point_access(
        r,
        nodes_poi_dist,
        node_index,
        thresholds,
        specs,
        config,
        access_prefixes=[ACCESS_PREFIX],
        nodes_counts=nodes_counts,
        diversity=sets,
        diversity_prefixes=(COUNT_PREFIX, DIVERSITY_PREFIX, RICHNESS_PREFIX),
    )

    print(f'  Saving {SAMPLE_POINT_TABLE} to database...')
    sample_points.columns = [
        'geom' if x == 'geometry' else x for x in sample_points.columns
    ]
    sample_points = sample_points.set_geometry('geom')
    with r.engine.connect() as connection:
        sample_points.to_postgis(
            SAMPLE_POINT_TABLE,
            connection,
            index=True,
            if_exists='replace',
        )
    print(f'  Wrote {SAMPLE_POINT_TABLE} ({len(sample_points)} points).')
    reached = {
        c: int(sample_points[c].sum())
        for c in sample_points.columns
        if c.startswith(ACCESS_PREFIX)
    }
    print(f'  Sample points with walking access: {reached}')
    beyond = {
        c: int(sample_points[c].sum())
        for c in sample_points.columns
        if c.startswith(BEYOND_PREFIX)
    }
    if beyond:
        print(f'  Sample points beyond an avoided destination: {beyond}')
    scored = [
        c for c in sample_points.columns if c.startswith(DIVERSITY_PREFIX)
    ]
    if scored:
        print('  Mean diversity of reachable destinations:')
        for column in scored:
            print(f'    {column}: {sample_points[column].mean():.3f}')
    script_running_log(r.config, script, task, start)
    r.engine.dispose()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    pedestrian_accessibility(codename)


if __name__ == '__main__':
    main()
