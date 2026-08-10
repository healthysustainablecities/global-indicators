"""
Cycling accessibility.

Optional GHSCI analysis step, gated by the region configuration flag
``cycling_indicators: true``.  Computes cycling accessibility to destinations over the
LTS-classified network produced by ``_cycling_lts_network`` (run that first), reusing
the destination-node lookup engine (``setup_sp.build_dest_node_lookup`` /
``_dist_from_lookup``) or the equivalent in-memory Dijkstra.

Accessibility is calculated for a configurable set of *measures* (see ``MEASURES``),
each defining a routable subgraph and cost: a strict low-stress measure (fully
LTS <= 2 routes, geometric distance), an optional stricter LTS-1-only variant, and a
danger-weighted measure (all streets routable, higher-stress length penalised).  Which
measures run is driven by ``cycling_indicators.contrasts`` — ordered measure pairs the
validation report juxtaposes (default: low_stress vs danger_weighted) — plus any
extras listed under ``cycling_indicators.measures``.

A configurable list of destination "specs" is analysed (default: fresh food, public open
space and public transport, each in a stricter and a less-strict / pooled variant), plus
a composite "all categories" indicator per variant.  Writes, per sample point and
measure, to the ``sample_points_cycling`` table (measure column infixes: ``lts1_``,
``safe_`` for LTS <= 2, none for danger-weighted):
    sp_cycle_<infix>nearest_node_<name>       distance (m) to the nearest destination
    sp_cycle_<infix>access_<name>_<d>m        binary access within d metres (1 / 0)
    sp_cycle_<infix>access_all_<variant>_<d>m composite: all of a variant's categories

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
    cal_dist_nodes_to_nearest_pois_inmemory,
    create_full_nodes,
    drop_dest_node_lookup,
    load_network_graph,
)
from sqlalchemy import text

DIST_COST = 'cost_dist'              # geometric reachability (low-stress measures)
CYCLE_COST = 'cost_lts'              # danger-weighted (access measure)
CYCLE_REVERSE_COST = 'cost_lts_reverse'
ROUTABLE_WHERE = 'bike_permitted OR foot_dismount'
SAFE_WHERE = 'lvl_traf_stress <= 2 AND (bike_permitted OR foot_dismount)'
# no-dismount counterpart of SAFE_WHERE: links that can be *ridden*.  foot_dismount
# is defined as the complement of bike_permitted on footway/path/pedestrian classes
# (_cycling_lts_network.compute_foot_dismount), so dropping the dismount term leaves
# exactly the rideable low-stress network — and cost_dist on those links is plain
# length, so no new edge cost column is needed.
RIDE_SAFE_WHERE = 'lvl_traf_stress <= 2 AND bike_permitted'
SAFE_COMP_TABLE = '_cycle_safe_comp'

# Accessibility measures (manuscript section 2.4).  Each measure routes the same
# origins and destinations over its own subgraph (``where``) and cost, writing results
# under its column ``infix``: sp_cycle_<infix>nearest_node_<name> distances and
# sp_cycle_<infix>access_<name>_<d>m binaries on sample_points_cycling, aggregated to
# pct_access_cycle_<infix>* / avg_cycle_dist_<infix>* grid and (pop_-prefixed) city
# columns by _12_aggregation.  Most measures allow footway dismount (walk the bike;
# walked distance counted, penalised by dismount_weight in the cost columns), so their
# routable set includes ``foot_dismount`` — footways are LTS 1 and remain in those
# low-stress subgraphs.  ``low_stress_ride`` is the deliberate exception.
#
#   * low_stress (the manuscript headline "safe" measure): reachable within the
#     *geometric* distance band by a fully low-stress route — routed over the LTS<=2
#     network (rideable LTS 1-2 plus walkable footways) on ``cost_dist``.
#   * low_stress_ride (dismount sensitivity permutation): as low_stress but the route
#     must be *ridden* throughout — links the rider would have to dismount and walk
#     are excluded.  Contrasting it with low_stress isolates the access that depends
#     on walking the bike, e.g. along a footpath beside an arterial or across a
#     hostile intersection; the gap is a candidate signal for where cycling
#     infrastructure would do the most work (see the dmgap_ columns below).
#   * lts1 (optional stricter sensitivity variant): as low_stress but the route must
#     stay entirely on LTS 1 (all-ages-and-abilities) links.
#   * danger_weighted (benefit-of-the-doubt secondary): reachable within the
#     *danger-weighted* band over the full routable network on ``cost_lts`` (LTS 3-4
#     usable at a proportionate penalty).
#
# Where both low_stress and low_stress_ride are computed, the paired per-sample-point
# contrast is derived as sp_cycle_dmgap_extra_<name> (extra metres of riding needed to
# avoid dismounting) and sp_cycle_dmgap_access_<name>_<d>m (access that exists only
# because the rider may dismount); see ``dismount_gap_columns``.
#
# ``label``/``short`` are the display names used by the validation report.
MEASURES = {
    'lts1': {
        'infix': 'lts1_',
        'cost': DIST_COST, 'reverse_cost': DIST_COST,
        'where': 'lvl_traf_stress <= 1 AND (bike_permitted OR foot_dismount)',
        'label': 'Low-stress route (LTS 1 only)', 'short': 'LS1',
        'description': 'geometric, fully LTS<=1 incl. footway dismount',
    },
    'low_stress_ride': {
        'infix': 'ride_',
        'cost': DIST_COST, 'reverse_cost': DIST_COST,
        'where': RIDE_SAFE_WHERE,
        'label': 'Low-stress ride, no dismount (LTS 1–2)', 'short': 'LSR',
        'description': 'geometric, fully LTS<=2, ridden throughout (no dismount)',
    },
    'low_stress': {
        'infix': 'safe_',
        'cost': DIST_COST, 'reverse_cost': DIST_COST,
        'where': SAFE_WHERE,
        'label': 'Low-stress route (LTS 1–2)', 'short': 'LS',
        'description': 'geometric, fully LTS<=2 incl. footway dismount',
    },
    # NOTE: the measure key, column infix and ``danger_weight`` constant are kept
    # for continuity with existing region configurations and result columns; only
    # the display terminology is "stress penalty".
    'danger_weighted': {
        'infix': '',
        'cost': CYCLE_COST, 'reverse_cost': CYCLE_REVERSE_COST,
        'where': ROUTABLE_WHERE,
        'label': 'Stress penalty route', 'short': 'SP',
        'description': 'stress penalty applied, full routable network',
    },
}
# canonical presentation/aggregation order: strictest to most permissive
MEASURE_ORDER = ['lts1', 'low_stress_ride', 'low_stress', 'danger_weighted']
# measure pairs whose paired per-sample-point contrast is derived automatically
# whenever both members are computed: (no-dismount variant, dismount-allowing base)
DISMOUNT_PAIR = ('low_stress_ride', 'low_stress')
DMGAP_INFIX = 'dmgap_'
# contrasts = ordered measure pairs the validation report juxtaposes (first pair =
# the established headline contrast); every measure named in a contrast is computed
DEFAULT_CONTRASTS = [['low_stress', 'danger_weighted']]


def resolve_contrasts(config):
    """Configured accessibility contrasts as an ordered list of measure-key pairs.

    ``cycling_indicators.contrasts`` is a list of two-item lists of measure keys
    (see ``MEASURES``); absent/empty falls back to ``DEFAULT_CONTRASTS``.
    """
    raw = (config or {}).get('contrasts') or DEFAULT_CONTRASTS
    contrasts = []
    for pair in raw:
        pair = [str(m) for m in pair]
        if len(pair) != 2:
            sys.exit(
                f'cycling_indicators.contrasts entries must be pairs of measures; '
                f'got {pair} (available: {MEASURE_ORDER})',
            )
        for m in pair:
            if m not in MEASURES:
                sys.exit(
                    f"Unknown accessibility measure '{m}' in "
                    f'cycling_indicators.contrasts (available: {MEASURE_ORDER})',
                )
        contrasts.append(pair)
    return contrasts


def resolve_measures(config):
    """Ordered unique measure keys to compute.

    The union of the measures named in ``cycling_indicators.contrasts`` and any
    extras listed under ``cycling_indicators.measures``, in ``MEASURE_ORDER``.
    """
    wanted = {m for pair in resolve_contrasts(config) for m in pair}
    for m in (config or {}).get('measures') or []:
        if m not in MEASURES:
            sys.exit(
                f"Unknown accessibility measure '{m}' in "
                f'cycling_indicators.measures (available: {MEASURE_ORDER})',
            )
        wanted.add(str(m))
    return [m for m in MEASURE_ORDER if m in wanted]

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


def derive_activity_centres(r, config, specs, n_workers=None, engine='pgrouting'):
    """Derive activity-centre destination layers and return them as new specs.

    For each configured tier, identifies network nodes whose pedestrian walk-shed
    (``walk_threshold`` m) reaches at least one destination of every required category
    (the tier's ``variant`` of each), materialises those nodes as a destination layer,
    and returns a spec per non-empty tier so cycling access can be measured to them.

    The pedestrian walk-distance lookup honours the resolved ``routing_engine``:
    'pgrouting' (pgr_drivingDistance lookup table) or 'inmemory' (equivalent
    in-process Dijkstra via cal_dist_nodes_to_nearest_pois_inmemory).
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
    if engine == 'inmemory':
        member_columns = []
        for _, _, _, members in plans:
            for m in members:
                entry = (m['layer'], f"_walk_{m['name']}", m.get('where', ''))
                if entry not in member_columns:
                    member_columns.append(entry)
        walk_all = cal_dist_nodes_to_nearest_pois_inmemory(
            r, member_columns, max_walk, node_index,
        )
    else:
        build_dest_node_lookup(
            r, active_layers=needed_layers, distance=max_walk,
            n_workers=n_workers,
        )
    new_specs = []
    for def_name, tier, walk, members in plans:
        if engine == 'inmemory':
            walk_dist = walk_all[
                [f"_walk_{m['name']}" for m in members]
            ].replace(-999, np.nan)
        else:
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
    if engine != 'inmemory':
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
        # ANALYZE so the planner has stats for the strict component double-join in
        # _safe_dist_from_lookup (it joins this table twice); without stats it can pick
        # a pathological plan (measured: strict aggregation 340s -> 0.3s with ANALYZE).
        conn.execute(text(f'ANALYZE {SAFE_COMP_TABLE}'))
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


def resolve_n_workers(config):
    """Resolve the number of concurrent pgRouting batch worker threads.

    Routing is CPU-bound (shortest-path expansion), so concurrency has a *low* optimum
    -- running one batch per core risks oversubscribing the CPU and slowing the routing
    phase rather than speeding it up.  Worker count is therefore deliberately NOT tied
    to ``multiprocessing`` (which drives the per-region PostgreSQL parallelism applied
    in _00_create_database.py, beneficial for the in-query aggregation phase but not for
    routing).  The optimal value should be confirmed by a controlled test on a network
    of representative size (note: the routable-network scope, ROUTABLE_WHERE, dominates
    routing cost far more than worker count).

    Precedence: an explicit ``cycling_indicators.workers`` override, else ``None`` --
    which lets ``build_dest_node_lookup`` use its conservative auto-detection
    (``min(4, cpu_count // 2)``).  Set ``workers`` explicitly only after testing on the
    target machine; values above ~half the physical cores typically slow routing down.
    """
    if isinstance(config, dict) and config.get('workers'):
        return int(config['workers'])
    return None


_ORIGIN_POOL = '_cyc_origin_pool'
_DEST_TABLE = '_cyc_dest'
_FOUND_TABLE = '_cyc_found'
_ORIGIN_SEED = '_cyc_origin_seed'


def _build_origin_pool(r):
    """Distinct sample-point terminal nodes = the routing origins.  Returns their index.

    Because footways are routable (dismount), a sample point's terminal nodes are always in
    the routable graph, so no cycling-aware snapping is needed -- footway-embedded points
    route out along footways (walked distance counted).
    """
    with r.engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS {_ORIGIN_POOL}'))
        conn.execute(text(
            f'CREATE TABLE {_ORIGIN_POOL} AS '
            f'SELECT DISTINCT osmid FROM ('
            f'  SELECT n1::bigint AS osmid FROM urban_sample_points WHERE n1 IS NOT NULL '
            f'  UNION SELECT n2::bigint FROM urban_sample_points WHERE n2 IS NOT NULL'
            f') s',
        ))
        conn.execute(text(f'CREATE INDEX ON {_ORIGIN_POOL} (osmid)'))
    osmids = r.get_df(f'SELECT osmid FROM {_ORIGIN_POOL}')['osmid'].astype('int64')
    return pd.Index(osmids, name='osmid')


def _build_dest_table(r, specs):
    """Materialise (spec, dest_node, offset) for every spec once (shared by both measures)."""
    with r.engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS {_DEST_TABLE}'))
        conn.execute(text(
            f'CREATE TABLE {_DEST_TABLE} (spec text, dest_node bigint, offset_m float)',
        ))
        for s in specs:
            layer, where, name = s['layer'], s.get('where', ''), s['name']
            for col, off in (('n1', 'n1_distance'), ('n2', 'n2_distance')):
                conds = [f'{col} IS NOT NULL']
                if where:
                    conds.append(f'({where})')
                conn.execute(
                    text(
                        f'INSERT INTO {_DEST_TABLE} (spec, dest_node, offset_m) '
                        f'SELECT :name, {col}::bigint, {off}::float '
                        f'FROM {layer} WHERE {" AND ".join(conds)}',
                    ),
                    {'name': name},
                )
        conn.execute(text(f'CREATE INDEX ON {_DEST_TABLE} (dest_node)'))


def _banded_distances(r, specs, bands, node_index, cost, reverse_cost, where,
                      col_prefix, n_workers):
    """Origin-seeded banded nearest-distance to each spec (one measure).

    For each ascending band, routes only the origins that have not yet reached every spec,
    records each spec's exact first-found distance, and carries covered origins forward.
    Returns a DataFrame indexed by origin osmid, one column ``col_prefix + spec`` per spec.
    """
    bands = sorted(bands)
    n_specs = len(specs)
    with r.engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS {_FOUND_TABLE}'))
        conn.execute(text(
            f'CREATE TABLE {_FOUND_TABLE} (osmid bigint, spec text, dist float)',
        ))
    for band in bands:
        remaining = r.get_df(
            f'SELECT p.osmid FROM {_ORIGIN_POOL} p WHERE ('
            f'  SELECT count(DISTINCT spec) FROM {_FOUND_TABLE} f WHERE f.osmid = p.osmid'
            f') < {n_specs}',
        )['osmid'].astype('int64').tolist()
        if not remaining:
            break
        _write_node_seed_layer(r, _ORIGIN_SEED, remaining)
        build_dest_node_lookup(
            r, active_layers=[_ORIGIN_SEED], distance=band, edge_table='edges',
            cost=cost, reverse_cost=reverse_cost, where=where, n_workers=n_workers,
        )
        with r.engine.begin() as conn:
            conn.execute(text(
                f'CREATE INDEX IF NOT EXISTS _dnl_node_idx ON _dest_node_lookup (node)',
            ))
            conn.execute(text('ANALYZE _dest_node_lookup'))
            conn.execute(text(
                f'INSERT INTO {_FOUND_TABLE} (osmid, spec, dist) '
                f'SELECT l.start_vid, d.spec, MIN(l.dist + COALESCE(d.offset_m, 0)) '
                f'FROM _dest_node_lookup l JOIN {_DEST_TABLE} d ON l.node = d.dest_node '
                f'WHERE NOT EXISTS ('
                f'  SELECT 1 FROM {_FOUND_TABLE} f '
                f'  WHERE f.osmid = l.start_vid AND f.spec = d.spec) '
                f'GROUP BY l.start_vid, d.spec '
                f'HAVING MIN(l.dist + COALESCE(d.offset_m, 0)) <= {band}',
            ))
        drop_dest_node_lookup(r)
    found = r.get_df(f'SELECT osmid, spec, dist FROM {_FOUND_TABLE}')
    if found.empty:
        frame = pd.DataFrame({s['name']: np.nan for s in specs}, index=node_index)
    else:
        frame = found.pivot_table(
            index='osmid', columns='spec', values='dist', aggfunc='min',
        ).reindex(node_index)
        for s in specs:  # specs never found anywhere -> all-NaN column
            if s['name'] not in frame.columns:
                frame[s['name']] = np.nan
        frame = frame[[s['name'] for s in specs]]
    frame.columns = [f'{col_prefix}{c}' for c in frame.columns]
    return frame


def _nearest_distances_inmemory(
    r, specs, max_band, node_index, cost, reverse_cost, where, col_prefix,
    collect=None,
):
    """Exact per-origin nearest distance to each spec via in-memory Dijkstra (one measure).

    Equivalent by construction to the banded pgRouting path (same graph, same edge
    costs, exact shortest paths): for each spec, a virtual super-source is connected
    to the spec's destination nodes at their offset cost, so a single multi-source
    C-level Dijkstra pass yields every node's ``MIN(network_dist + offset)`` — the
    same quantity the banded lookup aggregates, without banding, batching or
    coverage bookkeeping.  Distances beyond ``max_band`` are NaN (never found within
    the largest threshold, exactly as the banded search leaves them).

    The whole computation is small: the graph is a few hundred thousand edges
    (~tens of MB as CSR) and each pass allocates one float array per node, so it is
    suitable for modest hardware.

    ``collect``, if given, is called as ``collect(spec_name, dist, pred, node_ids)``
    with this pass's shortest-path tree (scipy's predecessor array costs one extra
    int32 array and no extra search).  It must consume the arrays before returning:
    ``dist`` is trimmed in place immediately afterwards.
    """
    from scipy.sparse import csr_matrix, hstack, vstack
    from scipy.sparse.csgraph import dijkstra

    graph, node_ids = load_network_graph(
        r, cost=cost, reverse_cost=reverse_cost, where=where,
    )
    n = graph.shape[0]
    dest = r.get_df(
        f'SELECT spec, dest_node, COALESCE(offset_m, 0)::float AS offset_m '
        f'FROM {_DEST_TABLE}',
    )
    # origin nodes absent from this measure's subgraph are unreachable (NaN row)
    origin_ids = node_index.to_numpy(dtype='int64')
    origin_pos = np.searchsorted(node_ids, origin_ids)
    origin_pos_clipped = np.clip(origin_pos, 0, n - 1)
    origin_in_graph = node_ids[origin_pos_clipped] == origin_ids

    origin_lookup = pd.Series(
        np.arange(len(origin_ids)), index=origin_ids,
    )

    frame = {}
    # a 0.5 m guard on the exploration limit so nodes at exactly the threshold are
    # visited (pgr_drivingDistance is inclusive); exact values are kept regardless
    limit = float(max_band) + 0.5
    for s in specs:
        name = s['name']
        rows = dest[dest['spec'] == name]
        pos = np.searchsorted(node_ids, rows['dest_node'].to_numpy('int64'))
        pos_clipped = np.clip(pos, 0, n - 1)
        in_graph = node_ids[pos_clipped] == rows['dest_node'].to_numpy('int64')
        col = np.full(len(origin_ids), np.nan)
        if in_graph.any():
            seed_pos = pos_clipped[in_graph]
            seed_off = rows['offset_m'].to_numpy('float64')[in_graph]
            # dedupe seeds sharing a node at their minimum offset
            seed = pd.DataFrame({'pos': seed_pos, 'off': seed_off}).groupby(
                'pos', as_index=False,
            )['off'].min()
            # augment with a super-source (index n) wired to each seed at its offset
            super_row = csr_matrix(
                (seed['off'], (np.zeros(len(seed), dtype=int), seed['pos'])),
                shape=(1, n),
            )
            aug = vstack(
                [
                    hstack([graph, csr_matrix((n, 1))]),
                    hstack([super_row, csr_matrix((1, 1))]),
                ],
                format='csr',
            )
            if collect is None:
                dist = dijkstra(aug, directed=True, indices=n, limit=limit)[:n]
            else:
                dist, pred = dijkstra(
                    aug, directed=True, indices=n, limit=limit,
                    return_predecessors=True,
                )
                dist = dist[:n]
                collect(name, dist, pred[:n], node_ids)
            dist[dist > max_band] = np.nan
            col = np.where(origin_in_graph, dist[origin_pos_clipped], np.nan)
        # identity co-location: a destination sharing an origin's network node is
        # reachable at its offset cost with no edge traversal, even where that node
        # has no edges in this measure's subgraph.  Matches pgr_drivingDistance,
        # which returns the seed vertex at cost 0 unconditionally — and the physical
        # reality that a co-located destination needs no route at all.
        at_origin = rows[rows['dest_node'].isin(origin_lookup.index)]
        if len(at_origin):
            best = at_origin.groupby('dest_node')['offset_m'].min()
            best = best[best <= max_band]
            if len(best):
                pos_o = origin_lookup[best.index].to_numpy()
                col[pos_o] = np.fmin(col[pos_o], best.to_numpy('float64'))
        frame[f'{col_prefix}{name}'] = col
    return pd.DataFrame(frame, index=node_index)


_PRIORITY_TABLE = 'cycling_dismount_priority'


def _origin_population_weights(r):
    """Population attributable to each network origin (sample-point terminal) node.

    Each sample point carries an equal share of its grid cell's population, credited
    to its nearer terminal node.  (``create_full_nodes`` blends both terminals when
    estimating a point's own distance; for accumulating route load onto links, one
    representative node per point is enough and much simpler to reason about.)
    """
    sp = r.get_df(
        'SELECT point_id, grid_id, n1, n1_distance, n2, n2_distance '
        'FROM urban_sample_points',
    )
    if sp.empty:
        return pd.Series(dtype='float64')
    pop = r.get_df(
        f"SELECT grid_id, pop_est FROM {r.config['grid_summary']}",
    )
    share = sp.groupby('grid_id')['point_id'].transform('size')
    sp = sp.merge(pop, on='grid_id', how='left')
    weight = sp['pop_est'].fillna(0).to_numpy('float64') / share.to_numpy('float64')
    nearer = np.where(
        sp['n2_distance'].notna() & (sp['n2_distance'] < sp['n1_distance']),
        sp['n2'], sp['n1'],
    )
    keep = pd.notna(nearer)
    return (
        pd.Series(weight[keep], index=pd.Index(nearer[keep].astype('int64')))
        .groupby(level=0).sum()
    )


class DismountPriority:
    """Population load carried by each link riders must dismount and walk.

    The router already computes, per destination type, one Dijkstra from a virtual
    super-source over every destination of that type; its predecessor array is the
    shortest-path *tree* of everyone's route to their nearest destination.  Adding
    each node's population weight to its parent, working from the furthest node
    inwards, gives every link the population routed over it in a single O(n) pass —
    no extra routing.  Read off the ``foot_dismount`` links only:

    * ``dm_pop_served`` — population whose nearest-destination low-stress route
      walks this link, summed over destination types: resident-destination
      *journeys*, not distinct residents (``dm_specs`` says how many types
      contribute, so ``served / dm_specs`` brackets it from below).
    * ``dm_pop_dependent`` — the same, restricted to residents with no low-stress
      route to that destination type within ``band`` when dismount links are
      excluded (i.e. whose access exists only because they may get off and walk).

    Caveats, to quote wherever the scores are published: a route crossing two
    dismount links contributes to both, so scores are a ranking, not an additive
    budget; and 'dependent' is measured against removing *all* dismount links, not
    this one alone.
    """

    def __init__(self, r, band, weights, ride_distances):
        self.band = float(band)
        self.weights = weights
        self.ride = ride_distances  # {spec name: Series indexed by node osmid}
        edges = r.get_df(
            'SELECT ogc_fid, "from" AS u, "to" AS v, length FROM edges '
            'WHERE foot_dismount',
        )
        # parallel edges: keep the shortest, matching load_network_graph's min-cost
        self.edge = {}
        for row in edges.itertuples(index=False):
            key = (min(row.u, row.v), max(row.u, row.v))
            prev = self.edge.get(key)
            if prev is None or (row.length or 0) < prev[1]:
                self.edge[key] = (int(row.ogc_fid), float(row.length or 0))
        self.served = {}
        self.dependent = {}
        self.specs = {}
        self.n_links = len(self.edge)

    def add(self, spec, dist, pred, node_ids):
        """Accumulate one spec's shortest-path tree onto the dismount links."""
        if not self.edge or self.weights.empty:
            return
        n = len(node_ids)
        weight = self.weights.reindex(node_ids).fillna(0).to_numpy('float64')
        if not weight.any():
            return
        reached = np.isfinite(dist) & (dist <= self.band)
        ride = self.ride.get(spec)
        if ride is None:
            dependent = np.zeros(n, dtype=bool)
        else:
            ride_dist = ride.reindex(node_ids).to_numpy('float64')
            with np.errstate(invalid='ignore'):
                dependent = reached & ~(ride_dist <= self.band)
        load = weight.copy()
        load_dep = np.where(dependent, weight, 0.0)

        # sum each subtree into its parent, furthest node first (a parent is always
        # strictly nearer than its child, so one ordered pass is exact)
        finite = np.isfinite(dist)
        order = np.argsort(np.where(finite, dist, np.inf), kind='stable')
        order = order[: int(finite.sum())].tolist()
        parent = pred.tolist()
        served, depend = load.tolist(), load_dep.tolist()
        for i in reversed(order):
            p = parent[i]
            if 0 <= p < n:
                served[p] += served[i]
                depend[p] += depend[i]

        ids = node_ids
        for i in order:
            p = parent[i]
            if not (0 <= p < n) or served[i] <= 0:
                continue
            u, v = int(ids[i]), int(ids[p])
            hit = self.edge.get((min(u, v), max(u, v)))
            if hit is None:
                continue
            fid = hit[0]
            self.served[fid] = self.served.get(fid, 0.0) + served[i]
            self.dependent[fid] = self.dependent.get(fid, 0.0) + depend[i]
            self.specs[fid] = self.specs.get(fid, 0) + 1

    def write(self, r):
        """Write the scored links to ``cycling_dismount_priority``."""
        if not self.served:
            print(
                '  - dismount priority: no dismount links carry any routed '
                'population; nothing written',
            )
            return
        scores = pd.DataFrame(
            {
                'ogc_fid': list(self.served),
                'dm_pop_served': [
                    round(v, 1) for v in self.served.values()
                ],
                'dm_pop_dependent': [
                    round(self.dependent.get(k, 0.0), 1) for k in self.served
                ],
                'dm_specs': [self.specs.get(k, 0) for k in self.served],
            },
        )
        scores.to_sql('_dismount_scores', r.engine, if_exists='replace', index=False)
        with r.engine.begin() as conn:
            conn.execute(text(f'DROP TABLE IF EXISTS {_PRIORITY_TABLE}'))
            conn.execute(text(
                f'CREATE TABLE {_PRIORITY_TABLE} AS '
                f'SELECT e.ogc_fid, e.osmid, e.name, e.highway, e.length, '
                f's.dm_pop_served, s.dm_pop_dependent, s.dm_specs, e.geom '
                f'FROM edges e JOIN _dismount_scores s USING (ogc_fid)',
            ))
            conn.execute(text(
                f'CREATE INDEX ON {_PRIORITY_TABLE} (dm_pop_dependent DESC)',
            ))
            conn.execute(text('DROP TABLE IF EXISTS _dismount_scores'))
        used = len(self.served)
        dependent = sum(1 for v in self.dependent.values() if v > 0)
        print(
            f'  - dismount priority: {used} of {self.n_links} dismount links carry '
            f'routed population ({dependent} carry access that depends on them); '
            f'wrote {_PRIORITY_TABLE}',
        )


def cycling_poi_distance(
    r, thresholds, specs, measures, n_workers=None, engine='pgrouting',
    dismount_priority=False,
):
    """Origin-seeded nearest-distance to each destination spec, per configured measure.

    Returns ``(nodes_poi_dist, node_index)`` where ``nodes_poi_dist`` is indexed by origin
    (sample-point terminal) node and has one column per (measure, spec):
    ``sp_cycle_<infix>nearest_node_<name>`` — the measure's routing distance to the
    nearest destination over its subgraph and cost (see ``MEASURES``).

    With the pgrouting engine each measure is routed band-by-band over the sorted
    ``thresholds``, re-routing only the origins that have not yet reached every spec, so
    the expensive outer bands touch only the few stragglers.

    ``dismount_priority`` additionally scores the links riders must dismount and walk
    from the dismount-allowing measure's shortest-path trees (see ``DismountPriority``);
    it needs the in-memory engine, which is the only one that exposes them.
    """
    bands = sorted(set(int(t) for t in thresholds))
    _ensure_node_associations(r, {s['layer'] for s in specs})
    node_index = _build_origin_pool(r)
    _build_dest_table(r, specs)

    frames = []
    priority, ride_distances = None, {}
    if engine == 'inmemory':
        max_band = bands[-1]
        print(
            f'  In-memory routing (exact, one Dijkstra pass per spec x measure, '
            f'max distance {max_band} m) over {len(node_index)} origins',
        )
    else:
        print(f'  Banded routing ({len(bands)} bands: {bands}) over {len(node_index)} origins')
    ride_key, base_key = DISMOUNT_PAIR
    for key in measures:
        m = MEASURES[key]
        prefix = f'sp_cycle_{m["infix"]}nearest_node_'
        print(f'  - {key} measure ({m["description"]})...')
        if engine == 'inmemory':
            collect = None
            if dismount_priority and key == base_key:
                # MEASURE_ORDER puts the no-dismount variant first, so its per-node
                # distances are already in hand to mark dismount-dependent origins
                band = 2000 if 2000 in bands else bands[-1]
                priority = DismountPriority(
                    r, band, _origin_population_weights(r), ride_distances,
                )
                print(
                    f'    (scoring {priority.n_links} dismount links from this '
                    f"measure's route trees, {band} m band)",
                )
                collect = priority.add
            frame = _nearest_distances_inmemory(
                r, specs, max_band, node_index, m['cost'], m['reverse_cost'],
                m['where'], prefix, collect=collect,
            )
            if dismount_priority and key == ride_key:
                ride_distances.update({
                    s['name']: frame[f'{prefix}{s["name"]}'] for s in specs
                    if f'{prefix}{s["name"]}' in frame.columns
                })
            frames.append(frame)
        else:
            frames.append(_banded_distances(
                r, specs, bands, node_index, m['cost'], m['reverse_cost'],
                m['where'], prefix, n_workers,
            ))
    if priority is not None:
        priority.write(r)
    for t in (_ORIGIN_POOL, _DEST_TABLE, _FOUND_TABLE, _ORIGIN_SEED):
        with r.engine.begin() as conn:
            conn.execute(text(f'DROP TABLE IF EXISTS {t}'))

    nodes_poi_dist = pd.concat(frames, axis=1)
    nodes_poi_dist = round(nodes_poi_dist, 0).astype('Int64')
    return nodes_poi_dist, node_index


def cycling_sample_point_access(
    r, nodes_poi_dist, node_index, thresholds, specs, config, measures,
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
    # Binary access per threshold.  Build all the access columns as standalone
    # frames and join them in one pd.concat rather than assigning column blocks
    # into the GeoDataFrame one threshold at a time: repeated insertion into a
    # frame that already holds 100+ columns fragments it, triggering pandas'
    # PerformanceWarning and O(ncols^2) recopying on large cities.
    access_frames = []
    for threshold in thresholds:
        access_names = [
            f"{x.replace('nearest_node', 'access')}_{threshold}m"
            for x in distance_names
        ]
        scores = binary_access_score(sample_points, distance_names, threshold)
        # binary_access_score returns the distance_names columns in order; rename
        # positionally to the per-threshold access names (as the block assignment did)
        scores.columns = access_names
        access_frames.append(scores)
    sample_points = pd.concat([sample_points] + access_frames, axis=1)

    # composite "all categories reachable" access, per named combined-access set and
    # strictness variant.  Each category contributes the spec matching the variant
    # (else its sole spec, so a single-variant custom category joins both).  The
    # 'standard' set keeps bare all_<variant> names for comparability; other sets are
    # namespaced all_<set>_<variant>.  Composites reference only per-spec access
    # columns (never other composites), so they are accumulated and concatenated once.
    sets = combined_access_sets(config, specs)
    axis = [v for v in ('strict', 'lenient') if any(s.get('variant') == v for s in specs)]
    available = set(sample_points.columns)
    composites = {}
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
            # composites for every configured measure
            for measure in (
                f'sp_cycle_{MEASURES[k]["infix"]}access_' for k in measures
            ):
                for threshold in thresholds:
                    cols = [
                        f'{measure}{n}_{threshold}m'
                        for n in names
                        if f'{measure}{n}_{threshold}m' in available
                    ]
                    if len(cols) >= 2:
                        col = f'{measure}all_{infix}{variant}_{threshold}m'
                        composites[col] = (
                            sample_points[cols].fillna(0).astype(int).prod(axis=1)
                        )
    if composites:
        sample_points = pd.concat(
            [sample_points, pd.DataFrame(composites, index=sample_points.index)],
            axis=1,
        )
    return dismount_gap_columns(sample_points, measures)


def dismount_gap_columns(sample_points, measures):
    """Paired with/without-dismount contrast columns, per sample point.

    Where both members of ``DISMOUNT_PAIR`` were computed, every distance and access
    column of the dismount-allowing measure is matched against its no-dismount twin:

    * ``sp_cycle_dmgap_extra_<name>`` — extra metres of riding needed to reach the
      nearest destination without dismounting (NA where either route is missing, so
      the mean of this column is over points reachable *both* ways).
    * ``sp_cycle_dmgap_access_<name>_<d>m`` — 1 where the point has access at that
      threshold only because the rider may dismount and walk.

    The contrast has to be made point by point: aggregating each measure first and
    differencing the means would compare averages taken over different (differently
    reachable) subsets of points.  Composite "all categories" access columns are
    picked up here too, since they are already in the frame.
    """
    ride, base = DISMOUNT_PAIR
    if not {ride, base}.issubset(set(measures)):
        return sample_points
    ride_infix, base_infix = MEASURES[ride]['infix'], MEASURES[base]['infix']
    dist_prefix = f'sp_cycle_{base_infix}nearest_node_'
    access_prefix = f'sp_cycle_{base_infix}access_'
    gap = {}
    for col in list(sample_points.columns):
        if col.startswith(dist_prefix):
            stem = col[len(dist_prefix):]
            twin = f'sp_cycle_{ride_infix}nearest_node_{stem}'
            if twin in sample_points.columns:
                gap[f'sp_cycle_{DMGAP_INFIX}extra_{stem}'] = (
                    sample_points[twin] - sample_points[col]
                )
        elif col.startswith(access_prefix):
            stem = col[len(access_prefix):]  # already carries the _<d>m suffix
            twin = f'sp_cycle_{ride_infix}access_{stem}'
            if twin in sample_points.columns:
                has = sample_points[col].fillna(0).astype(int)
                rides = sample_points[twin].fillna(0).astype(int)
                gap[f'sp_cycle_{DMGAP_INFIX}access_{stem}'] = (
                    (has == 1) & (rides == 0)
                ).astype(int)
    if not gap:
        return sample_points
    return pd.concat(
        [sample_points, pd.DataFrame(gap, index=sample_points.index)], axis=1,
    )


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
    if 'cost_dist' not in _table_columns(r, 'edges'):
        sys.exit(
            'edges has no cost_dist column; run _cycling_lts_network first.',
        )

    # thresholds double as the routing bands; keep them ascending and de-duplicated.
    thresholds = tuple(sorted(set(config.get('distances') or (500, 1000, 2000, 5000))))
    specs = usable_destination_specs(
        r, config.get('destinations') or DEFAULT_DESTINATIONS,
    )
    if not specs:
        sys.exit('No cycling destination layers available to analyse.')

    # cycling_indicators.routing_engine takes precedence; falls back to the
    # region's top-level routing_engine (shared with the pedestrian analysis)
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

    measures = resolve_measures(config)
    print('\nCalculating cycling safe-route accessibility...')
    print(f"  Destinations: {', '.join(s['name'] for s in specs)}")
    print(f"  Measures: {', '.join(measures)}")
    # derive activity-centre (destination cluster) layers, then analyse them as
    # additional destinations alongside the configured specs
    n_workers = resolve_n_workers(config)
    specs = specs + derive_activity_centres(
        r, config, specs, n_workers=n_workers, engine=engine,
    )
    # candidate cycling-infrastructure links: only meaningful when the dismount pair
    # is being contrasted, and only the in-memory engine exposes the route trees
    priority = bool(config.get('dismount_priority'))
    if priority and (
        engine != 'inmemory' or not set(DISMOUNT_PAIR).issubset(measures)
    ):
        print(
            '  Skipping dismount priority links: needs routing_engine inmemory and '
            f'both of {DISMOUNT_PAIR} among the configured measures.',
        )
        priority = False
    nodes_poi_dist, node_index = cycling_poi_distance(
        r, thresholds, specs, measures, n_workers=n_workers, engine=engine,
        dismount_priority=priority,
    )
    sample_points = cycling_sample_point_access(
        r, nodes_poi_dist, node_index, thresholds, specs, config, measures,
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
    print(f'  Wrote sample_points_cycling ({len(sample_points)} points).')
    for key in measures:
        # measure infixes precede 'access_', so each prefix matches only its own columns
        prefix = f'sp_cycle_{MEASURES[key]["infix"]}access_'
        reached = {
            c: int(sample_points[c].sum())
            for c in sample_points.columns if c.startswith(prefix)
        }
        print(f'  Sample points with {key} access: {reached}')
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
