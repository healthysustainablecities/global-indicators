"""
Shared accessibility specification.

Destinations and activity centres are not specific to any one mode of travel: a
region declares *what* it wants access measured to, and each analysis measures it
over its own network and cost.  This module holds that shared layer -- the
destination "specs", the activity-centre (destination cluster) definitions, the
combined-access sets, and the origin-seeded nearest-distance routing machinery --
so that both the pedestrian analysis (``_pedestrian_accessibility``) and the
cycling analysis (``_cycling_accessibility``) work from one specification.

A destination spec maps a GHSCI layer (optionally filtered by an SQL ``where``) to
an indicator ``name``, tagged by ``category`` and strictness ``variant``::

    {name: fresh_food_market, category: food, variant: strict,
     layer: destinations, where: "dest_name = 'fresh_food_market'"}

An *activity centre* is a network location whose pedestrian walk-shed
(``walk_threshold`` m) reaches at least one destination of every required
``category``.  Centres are materialised as derived destination layers
(``activity_centre_<infix><tier>``) and then measured like any other destination,
by whichever analyses are configured.

Region configuration (all keys optional; defaults reproduce prior behaviour)::

    accessibility:
      pedestrian:
        distances: [500, 1000, 1500]
      destinations: [...]
      activity_centres: {...}
      combined_access: {...}

``cycling_indicators.destinations`` / ``.activity_centres`` / ``.combined_access``
continue to take precedence for the cycling analysis, so existing configurations
are unaffected; anything they do not set is inherited from the shared block.

This module is imported by both analyses and holds no mode-specific logic; the
cycling module re-exports the names it moved from, so existing imports of
``_cycling_accessibility`` keep working.
"""

import numpy as np
import pandas as pd
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

# Default destination specs: each maps a GHSCI layer (optionally filtered by an SQL
# ``where``) to an indicator ``name``, tagged by ``category`` and strictness ``variant``
# so the composite "all categories" indicators can be derived per variant.
DEFAULT_DESTINATIONS = [
    {
        'name': 'fresh_food_market',
        'category': 'food',
        'variant': 'strict',
        'layer': 'destinations',
        'where': "dest_name = 'fresh_food_market'",
    },
    {
        'name': 'fresh_food_pooled',
        'category': 'food',
        'variant': 'lenient',
        'layer': 'destinations',
        'where': "dest_name IN ('fresh_food_market', 'convenience')",
    },
    {
        'name': 'public_open_space_large',
        'category': 'pos',
        'variant': 'strict',
        'layer': 'aos_public_large_nodes_30m_line',
    },
    {
        'name': 'public_open_space_any',
        'category': 'pos',
        'variant': 'lenient',
        'layer': 'aos_public_any_nodes_30m_line',
    },
    {
        'name': 'pt_frequent',
        'category': 'pt',
        'variant': 'strict',
        'layer': 'pt_stops_headway',
        'where': 'headway <= 20',
    },
    {
        'name': 'pt_any',
        'category': 'pt',
        'variant': 'lenient',
        'layer': 'destinations',
        'where': "dest_name = 'pt_any'",
    },
]

# Activity-centre (destination cluster) defaults.  An activity centre is a network
# location whose pedestrian walk-shed (``walk_threshold`` m) contains at least one
# destination of every required ``category``.  Two tiers are derived by default,
# mapping a tier name to the destination ``variant`` it is built from: a "local"
# (everyday) centre from the lenient variants and a "complete" (high-amenity) centre
# from the strict variants.  Access is then measured to the nearest centre of each
# tier, exactly like any other destination.  (INDICATOR_DESIGN.md §4.)
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

# Configuration keys a mode-specific block inherits from the shared ``accessibility``
# block when it does not set them itself.
SHARED_KEYS = (
    'destinations',
    'activity_centres',
    'combined_access',
    'diversity',
)


def accessibility_config(r):
    """The region's shared ``accessibility`` block as a mapping (empty if absent)."""
    config = (r.config or {}).get('accessibility')
    return config if isinstance(config, dict) else {}


def effective_config(shared, override):
    """Overlay a mode-specific configuration over the shared accessibility block.

    Only the keys both layers can express (``SHARED_KEYS``) are inherited, and only
    where the mode-specific block does not set them; every other key of ``override``
    is passed through untouched.  An explicit ``activity_centres: false`` therefore
    still disables activity centres for that mode, because ``False`` is a value.
    """
    out = dict(override or {})
    for key in SHARED_KEYS:
        if out.get(key) is None and (shared or {}).get(key) is not None:
            out[key] = shared[key]
    return out


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

    Enabled by default whenever the analysis is configured (``config`` is a mapping,
    possibly empty); set ``activity_centres: false`` to disable, or supply a mapping
    to override ``walk_threshold`` / ``categories`` / ``tiers``.
    """
    if not isinstance(config, dict):
        return None
    # enabled by default whenever the analysis is on (config is a mapping,
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
            {
                k: v
                for k, v in ac.items()
                if v is not None and k in RESERVED_AC_KEYS
            },
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
            if d is False or d is None:
                # an explicit false disables that definition, including the
                # implicit 'standard' one -- for a region whose own
                # threshold is the point, the global 400 m centre is just
                # extra columns
                defs.pop(name, None)
            elif isinstance(d, dict):
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
    global_cats = sorted(
        {
            s['category']
            for s in specs
            if s.get('category') and s.get('variant') in ('strict', 'lenient')
        },
    )
    sets = {STANDARD_SET: global_cats}
    for name, spec in ((config or {}).get('combined_access') or {}).items():
        categories = (spec or {}).get('categories')
        if categories:
            sets[name] = list(categories)
    return sets


# A diversity set's groups are measured as ordinary destination specs named
# ``<set>__<group>``; the doubled underscore keeps the set and group names
# separable however many underscores either of them contains.
DIVERSITY_GROUP_SEPARATOR = '__'


def diversity_sets(config):
    """Named diversity sets: ``set_name -> {layer, groups, distances}``.

    A diversity set declares the sub-types a category is considered to be made
    up of, each as an SQL condition over a destination layer.  Diversity is then
    how evenly the destinations reachable from a location are spread across those
    sub-types -- a different question from whether any of them is reachable at
    all, which is what the access indicators answer.  Somewhere with five
    bakeries and somewhere with a butcher, a greengrocer, a dairy and a
    supermarket score the same for access to food retail, and should not.

    Sets of fewer than two groups are skipped: diversity over one sub-type is
    always either zero or undefined, and reports nothing the count does not.
    """
    sets = {}
    for name, spec in ((config or {}).get('diversity') or {}).items():
        if not isinstance(spec, dict):
            continue
        groups = spec.get('groups') or {}
        if len(groups) < 2:
            print(
                f"  - skipping diversity set '{name}': fewer than two groups",
            )
            continue
        sets[name] = {
            'layer': spec.get('layer') or 'destinations',
            'groups': dict(groups),
            'distances': spec.get('distances'),
        }
    return sets


def diversity_specs(sets):
    """A destination spec for every group of every diversity set.

    Tagged with a per-set category and a ``group`` variant so that they are
    inert to the combined-access and activity-centre machinery, which considers
    only the strict and lenient variants.
    """
    return [
        {
            'name': f'{name}{DIVERSITY_GROUP_SEPARATOR}{group}',
            'category': f'diversity_{name}',
            'variant': 'group',
            'layer': s['layer'],
            'where': where,
        }
        for name, s in sets.items()
        for group, where in s['groups'].items()
    ]


def diversity_bands(sets, thresholds):
    """Every band any diversity set is evaluated at, ascending."""
    bands = set()
    for s in sets.values():
        bands.update(int(d) for d in (s['distances'] or thresholds))
    return tuple(sorted(bands))


def set_bands(s, thresholds):
    """The bands one diversity set is evaluated at, ascending."""
    return tuple(sorted({int(d) for d in (s['distances'] or thresholds)}))


def normalised_entropy(counts):
    """Normalised Shannon entropy of each row of a count frame, 0 to 1.

    ``H = -sum(p ln p) / ln k`` over the *k* configured groups.  Normalising by
    the configured *k* rather than by the number of groups that happen to be
    present locally is what makes the score comparable between places: a
    location reaching two of seven food sub-types should not score as though
    two were all there were.

    A location reaching nothing scores 0, not null.  Nothing available is no
    diversity, and recording it as missing would drop precisely the worst-served
    locations out of every mean computed afterwards.  A location reaching only
    one sub-type also scores 0, which is the same statement.
    """
    k = counts.shape[1]
    values = counts.to_numpy(dtype='float64')
    totals = values.sum(axis=1)
    with np.errstate(divide='ignore', invalid='ignore'):
        shares = np.where(totals[:, None] > 0, values / totals[:, None], 0.0)
        terms = np.where(shares > 0, shares * np.log(shares), 0.0)
    scores = -terms.sum(axis=1) / np.log(k)
    # negating a sum of zeros yields -0.0, which is the same number but reads as
    # a different one in an exported table
    scores[scores == 0] = 0.0
    return pd.Series(scores, index=counts.index)


def richness(counts):
    """Share of a diversity set's groups with anything reachable, 0 to 1.

    The plainer companion to the entropy: how many of the sub-types are
    available, ignoring how the destinations are distributed between them.
    """
    return (counts > 0).sum(axis=1) / counts.shape[1]


def _write_node_seed_layer(r, name, osmids):
    """Materialise a derived destination layer seeded directly at network nodes.

    The resulting table mimics a destination layer (n1/n2 + offsets) so it can be fed
    through the standard ``build_dest_node_lookup`` / ``_dist_from_lookup`` machinery:
    each centre node is its own seed with a zero offset.
    """
    with r.engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
    pd.DataFrame({'osmid': pd.Series(osmids, dtype='int64')}).to_sql(
        '_ac_seed',
        r.engine,
        if_exists='replace',
        index=False,
    )
    with r.engine.begin() as conn:
        conn.execute(
            text(
                f'CREATE TABLE "{name}" AS '
                f'SELECT n.osmid AS n1, NULL::bigint AS n2, '
                f'0.0::float AS n1_distance, NULL::float AS n2_distance, n.geom '
                f'FROM nodes n JOIN _ac_seed s ON n.osmid = s.osmid',
            ),
        )
        conn.execute(text('DROP TABLE IF EXISTS _ac_seed'))


def _plan_signature(walk, members):
    """Stable description of what an activity-centre layer was derived from.

    Stored as the layer's table comment so a second analysis in the same run can
    reuse a layer it would have derived identically, and re-derive one it would not.
    """
    parts = [f'{m["name"]}@{m["layer"]}:{m.get("where", "")}' for m in members]
    return f'walk={walk};members={"|".join(parts)}'


def _layer_signature(r, layer):
    """The recorded provenance of an existing activity-centre layer, or None."""
    signature = r.get_df(
        f"SELECT obj_description('public.\"{layer}\"'::regclass) AS s",
    )
    if signature.empty:
        return None
    value = signature['s'].iloc[0]
    return None if pd.isna(value) else str(value)


def derive_activity_centres(
    r,
    config,
    specs,
    n_workers=None,
    engine='pgrouting',
    reuse=True,
):
    """Derive activity-centre destination layers and return them as new specs.

    For each configured tier, identifies network nodes whose pedestrian walk-shed
    (``walk_threshold`` m) reaches at least one destination of every required category
    (the tier's ``variant`` of each), materialises those nodes as a destination layer,
    and returns a spec per non-empty tier so access can be measured to them.

    The pedestrian walk-distance lookup honours the resolved ``routing_engine``:
    'pgrouting' (pgr_drivingDistance lookup table) or 'inmemory' (equivalent
    in-process Dijkstra via cal_dist_nodes_to_nearest_pois_inmemory).

    Co-location is a property of the pedestrian network, not of the mode access is
    later measured in, so the pedestrian and cycling analyses derive the same layers.
    With ``reuse`` (the default), a layer already carrying the provenance this run
    would have written is kept rather than recomputed, so whichever analysis runs
    second pays nothing.
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

    def _spec(def_name, tier):
        infix = '' if def_name == STANDARD_SET else f'{def_name}_'
        layer = f'activity_centre_{infix}{tier}'
        return layer, {
            'name': layer,
            'category': 'activity_centre',
            'variant': f'{def_name}_{tier}',
            'layer': layer,
        }

    if reuse:
        # every planned layer already present and derived from the same members and
        # threshold: nothing to do (the other analysis in this run derived them)
        existing = set(r.get_tables())
        reusable = []
        for def_name, tier, walk, members in plans:
            layer, spec = _spec(def_name, tier)
            if layer not in existing or _layer_signature(r, layer) != (
                _plan_signature(walk, members)
            ):
                reusable = None
                break
            reusable.append(spec)
        if reusable:
            print(
                f'  Reusing {len(reusable)} previously derived activity centre '
                f'layer(s).',
            )
            return reusable

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
            r,
            member_columns,
            max_walk,
            node_index,
        )
    else:
        build_dest_node_lookup(
            r,
            active_layers=needed_layers,
            distance=max_walk,
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
                        r,
                        m['layer'],
                        m.get('where', ''),
                        node_index,
                        f"_walk_{m['name']}",
                    )
                    for m in members
                ],
                axis=1,
            ).replace(-999, np.nan)
        anchors = node_index[(walk_dist <= walk).all(axis=1).to_numpy()]
        osmids = anchors.astype('int64').tolist()
        layer, spec = _spec(def_name, tier)
        print(f'    {def_name}/{tier}: {len(osmids)} centre nodes')
        if not osmids:
            continue
        _write_node_seed_layer(r, layer, osmids)
        with r.engine.begin() as conn:
            conn.execute(
                text(
                    f'COMMENT ON TABLE "{layer}" IS :signature',
                ),
                {'signature': _plan_signature(walk, members)},
            )
        new_specs.append(spec)
    if engine != 'inmemory':
        drop_dest_node_lookup(r)
    return new_specs


def resolve_n_workers(config):
    """Resolve the number of concurrent pgRouting batch worker threads.

    Routing is CPU-bound (shortest-path expansion), so concurrency has a *low* optimum
    -- running one batch per core risks oversubscribing the CPU and slowing the routing
    phase rather than speeding it up.  Worker count is therefore deliberately NOT tied
    to ``multiprocessing`` (which drives the per-region PostgreSQL parallelism applied
    in _00_create_database.py, beneficial for the in-query aggregation phase but not for
    routing).  The optimal value should be confirmed by a controlled test on a network
    of representative size (note: the routable-network scope dominates routing cost far
    more than worker count).

    Precedence: an explicit ``workers`` override on the analysis configuration, else
    ``None`` -- which lets ``build_dest_node_lookup`` use its conservative
    auto-detection (``min(4, cpu_count // 2)``).  Set ``workers`` explicitly only after
    testing on the target machine; values above ~half the physical cores typically slow
    routing down.
    """
    if isinstance(config, dict) and config.get('workers'):
        return int(config['workers'])
    return None


# Transient routing scratch tables, shared by every analysis (dropped after use).
_ORIGIN_POOL = '_acc_origin_pool'
_DEST_TABLE = '_acc_dest'
_FOUND_TABLE = '_acc_found'
_ORIGIN_SEED = '_acc_origin_seed'
SCRATCH_TABLES = (_ORIGIN_POOL, _DEST_TABLE, _FOUND_TABLE, _ORIGIN_SEED)


def _build_origin_pool(r):
    """Distinct sample-point terminal nodes = the routing origins.  Returns their index.

    A sample point's terminal nodes are, by construction, nodes of the network the
    sample points were laid out on, so no mode-aware snapping is needed: on the
    cycling side footways are routable (dismount), so footway-embedded points route
    out along footways with the walked distance counted.
    """
    with r.engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS {_ORIGIN_POOL}'))
        conn.execute(
            text(
                f'CREATE TABLE {_ORIGIN_POOL} AS '
                f'SELECT DISTINCT osmid FROM ('
                f'  SELECT n1::bigint AS osmid FROM urban_sample_points WHERE n1 IS NOT NULL '
                f'  UNION SELECT n2::bigint FROM urban_sample_points WHERE n2 IS NOT NULL'
                f') s',
            ),
        )
        conn.execute(text(f'CREATE INDEX ON {_ORIGIN_POOL} (osmid)'))
    osmids = r.get_df(f'SELECT osmid FROM {_ORIGIN_POOL}')['osmid'].astype(
        'int64',
    )
    return pd.Index(osmids, name='osmid')


def _build_dest_table(r, specs):
    """Materialise (spec, dest_key, dest_node, offset) for every spec once.

    Shared by all passes.  ``dest_key`` numbers each *destination* within its spec,
    so that the two node attachments of one destination (``n1`` / ``n2``) are
    recognisable as the same thing: nearest-distance passes take a minimum and do
    not care, but counting a destination twice because it sits on an edge rather
    than at a node would overstate every count.  It is assigned by
    ``row_number()`` over the filtered layer rather than from a primary key,
    because destination layers do not share one -- ``destinations`` has
    ``dest_oid``, the open space node layers have ``aos_entryid``, and the derived
    activity centre layers have no key at all.
    """
    with r.engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS {_DEST_TABLE}'))
        conn.execute(
            text(
                f'CREATE TABLE {_DEST_TABLE} '
                f'(spec text, dest_key bigint, dest_node bigint, offset_m float)',
            ),
        )
        for s in specs:
            layer, where, name = s['layer'], s.get('where', ''), s['name']
            cond = f'WHERE {where}' if where else ''
            # both attachments emitted from one statement, so a destination's
            # dest_key is the same for each of them
            conn.execute(
                text(
                    f'INSERT INTO {_DEST_TABLE} (spec, dest_key, dest_node, offset_m) '
                    f'WITH d AS ('
                    f'  SELECT row_number() OVER () AS dest_key, '
                    f'         n1, n2, n1_distance, n2_distance '
                    f'    FROM {layer} {cond}'
                    f') '
                    f'SELECT :name, d.dest_key, v.node, v.off '
                    f'  FROM d CROSS JOIN LATERAL (VALUES '
                    f'    (d.n1::bigint, d.n1_distance::float), '
                    f'    (d.n2::bigint, d.n2_distance::float)'
                    f'  ) AS v(node, off) '
                    f' WHERE v.node IS NOT NULL',
                ),
                {'name': name},
            )
        conn.execute(text(f'CREATE INDEX ON {_DEST_TABLE} (dest_node)'))


def drop_scratch_tables(r):
    """Drop the transient routing scratch tables."""
    for t in SCRATCH_TABLES:
        with r.engine.begin() as conn:
            conn.execute(text(f'DROP TABLE IF EXISTS {t}'))


def _banded_distances(
    r,
    specs,
    bands,
    node_index,
    cost,
    reverse_cost,
    where,
    col_prefix,
    n_workers,
):
    """Origin-seeded banded nearest-distance to each spec (one routing pass).

    For each ascending band, routes only the origins that have not yet reached every spec,
    records each spec's exact first-found distance, and carries covered origins forward.
    Returns a DataFrame indexed by origin osmid, one column ``col_prefix + spec`` per spec.
    """
    bands = sorted(bands)
    n_specs = len(specs)
    with r.engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS {_FOUND_TABLE}'))
        conn.execute(
            text(
                f'CREATE TABLE {_FOUND_TABLE} (osmid bigint, spec text, dist float)',
            ),
        )
    for band in bands:
        remaining = (
            r.get_df(
                f'SELECT p.osmid FROM {_ORIGIN_POOL} p WHERE ('
                f'  SELECT count(DISTINCT spec) FROM {_FOUND_TABLE} f WHERE f.osmid = p.osmid'
                f') < {n_specs}',
            )['osmid']
            .astype('int64')
            .tolist()
        )
        if not remaining:
            break
        _write_node_seed_layer(r, _ORIGIN_SEED, remaining)
        build_dest_node_lookup(
            r,
            active_layers=[_ORIGIN_SEED],
            distance=band,
            edge_table='edges',
            cost=cost,
            reverse_cost=reverse_cost,
            where=where,
            n_workers=n_workers,
        )
        with r.engine.begin() as conn:
            conn.execute(
                text(
                    f'CREATE INDEX IF NOT EXISTS _dnl_node_idx ON _dest_node_lookup (node)',
                ),
            )
            conn.execute(text('ANALYZE _dest_node_lookup'))
            conn.execute(
                text(
                    f'INSERT INTO {_FOUND_TABLE} (osmid, spec, dist) '
                    f'SELECT l.start_vid, d.spec, MIN(l.dist + COALESCE(d.offset_m, 0)) '
                    f'FROM _dest_node_lookup l JOIN {_DEST_TABLE} d ON l.node = d.dest_node '
                    f'WHERE NOT EXISTS ('
                    f'  SELECT 1 FROM {_FOUND_TABLE} f '
                    f'  WHERE f.osmid = l.start_vid AND f.spec = d.spec) '
                    f'GROUP BY l.start_vid, d.spec '
                    f'HAVING MIN(l.dist + COALESCE(d.offset_m, 0)) <= {band}',
                ),
            )
        drop_dest_node_lookup(r)
    found = r.get_df(f'SELECT osmid, spec, dist FROM {_FOUND_TABLE}')
    if found.empty:
        frame = pd.DataFrame(
            {s['name']: np.nan for s in specs},
            index=node_index,
        )
    else:
        frame = found.pivot_table(
            index='osmid',
            columns='spec',
            values='dist',
            aggfunc='min',
        ).reindex(node_index)
        for s in specs:  # specs never found anywhere -> all-NaN column
            if s['name'] not in frame.columns:
                frame[s['name']] = np.nan
        frame = frame[[s['name'] for s in specs]]
    frame.columns = [f'{col_prefix}{c}' for c in frame.columns]
    return frame


def count_column(col_prefix, spec_name, band):
    """Name of the count column for a spec at a band.

    The band belongs in the name because a count, unlike a nearest distance, is
    only meaningful with respect to the catchment it was counted within.
    """
    return f'{col_prefix}{spec_name}_{band}m'


def _counts_frame(found, specs, bands, node_index, col_prefix):
    """Assemble a per-origin count frame from long (osmid, spec, band, n) records.

    Origins with no record for a spec reached nothing within the band, which is a
    count of zero rather than a missing value -- an unreachable origin genuinely
    has nothing available to it, and treating that as missing would drop exactly
    the worst-served locations out of any subsequent mean.
    """
    frame = pd.DataFrame(index=node_index)
    for s in specs:
        for band in bands:
            column = count_column(col_prefix, s['name'], band)
            if found.empty:
                frame[column] = 0
                continue
            match = found[
                (found['spec'] == s['name']) & (found['band'] == band)
            ]
            frame[column] = (
                match.set_index('osmid')['n'].reindex(node_index).fillna(0)
            )
    return frame.astype('int64')


def _banded_counts(
    r,
    specs,
    bands,
    node_index,
    cost,
    reverse_cost,
    where,
    col_prefix,
    n_workers,
):
    """Destinations of each spec reachable from each origin, per band (one pass).

    Unlike ``_banded_distances``, which stops routing an origin once it has found
    every spec, a count needs the whole catchment explored: one routing pass to
    the largest band, then the per-band counts read off it by conditional
    aggregation, so the lookup is scanned once however many bands are configured.
    """
    bands = sorted(bands)
    _write_node_seed_layer(
        r,
        _ORIGIN_SEED,
        node_index.astype('int64').tolist(),
    )
    build_dest_node_lookup(
        r,
        active_layers=[_ORIGIN_SEED],
        distance=max(bands),
        edge_table='edges',
        cost=cost,
        reverse_cost=reverse_cost,
        where=where,
        n_workers=n_workers,
    )
    try:
        with r.engine.begin() as conn:
            conn.execute(
                text(
                    'CREATE INDEX IF NOT EXISTS _dnl_node_idx '
                    'ON _dest_node_lookup (node)',
                ),
            )
            conn.execute(text('ANALYZE _dest_node_lookup'))
        # one COUNT(DISTINCT dest_key) per band; distinct because a destination
        # lying on an edge is attached at both of that edge's nodes
        aggregates = ', '.join(
            f'COUNT(DISTINCT d.dest_key) FILTER '
            f'(WHERE l.dist + COALESCE(d.offset_m, 0) <= {band}) AS "b{band}"'
            for band in bands
        )
        wide = r.get_df(
            f'SELECT l.start_vid AS osmid, d.spec, {aggregates} '
            f'FROM _dest_node_lookup l '
            f'JOIN {_DEST_TABLE} d ON l.node = d.dest_node '
            f'GROUP BY l.start_vid, d.spec',
        )
    finally:
        drop_dest_node_lookup(r)
    if wide.empty:
        found = pd.DataFrame(columns=['osmid', 'spec', 'band', 'n'])
    else:
        found = wide.melt(
            id_vars=['osmid', 'spec'],
            var_name='band',
            value_name='n',
        )
        found['band'] = found['band'].str[1:].astype(int)
    return _counts_frame(found, specs, bands, node_index, col_prefix)


# Target size, in floating point values, of the distance matrix one in-memory
# counting pass allocates.  scipy's dijkstra returns a full (seeds x nodes)
# matrix before it can be sliced down to the origins, so the chunk size has to
# come from the size of the network: a fixed chunk that is comfortable on a town
# allocates gigabytes on a large city.  8e6 values is ~64 MB.
_COUNT_PASS_VALUES = 8e6


def _counts_inmemory(
    r,
    specs,
    bands,
    node_index,
    cost,
    reverse_cost,
    where,
    col_prefix,
    chunk_size=None,
):
    """In-memory equivalent of ``_banded_counts`` (exact, one Dijkstra per chunk).

    Seeded from the *destinations* rather than the origins, because there are far
    fewer of them and each pass costs one output row per seed.  That reversal is
    sound only because ``load_network_graph`` builds a symmetric minimum-cost
    graph (both arcs of every edge carry the same weight, matching
    ``pgr_drivingDistance(..., directed := false)``), so the distance from a
    destination to an origin is the distance from the origin to the destination.

    Destinations are chunked with both of their node attachments kept together,
    so each destination's minimum over its attachments resolves within the chunk
    that produced it and no per-destination state is carried between chunks.  The
    chunk size is derived from the size of the network unless one is given, so
    that the memory a pass needs does not scale with the city.
    """
    from scipy.sparse.csgraph import dijkstra

    bands = sorted(bands)
    graph, node_ids = load_network_graph(
        r,
        cost=cost,
        reverse_cost=reverse_cost,
        where=where,
    )
    n = graph.shape[0]
    # a destination usually attaches at two nodes, so a chunk of k destinations
    # seeds up to 2k rows
    chunk_size = chunk_size or max(1, int(_COUNT_PASS_VALUES / max(n, 1) / 2))
    origin_ids = node_index.to_numpy(dtype='int64')
    origin_pos = np.clip(np.searchsorted(node_ids, origin_ids), 0, n - 1)
    # origins absent from this pass's subgraph can reach nothing
    origin_in_graph = node_ids[origin_pos] == origin_ids

    dest = r.get_df(
        f'SELECT spec, dest_key, dest_node, COALESCE(offset_m, 0)::float '
        f'AS offset_m FROM {_DEST_TABLE} ORDER BY spec, dest_key',
    )
    # a 0.5 m guard on the exploration limit so nodes at exactly the threshold
    # are visited, as pgr_drivingDistance includes them
    limit = float(max(bands)) + 0.5
    records = []
    for name, rows in dest.groupby('spec', sort=False):
        nodes = rows['dest_node'].to_numpy('int64')
        pos = np.clip(np.searchsorted(node_ids, nodes), 0, n - 1)
        rows = rows.assign(pos=pos)[node_ids[pos] == nodes]
        if rows.empty:
            continue
        keys = rows['dest_key'].drop_duplicates().to_numpy()
        totals = {b: np.zeros(len(origin_ids), dtype='int64') for b in bands}
        for start in range(0, len(keys), chunk_size):
            part = rows[
                rows['dest_key'].isin(keys[start : start + chunk_size])
            ]
            seeds, seed_row = np.unique(
                part['pos'].to_numpy(),
                return_inverse=True,
            )
            distances = dijkstra(
                graph,
                directed=True,
                indices=seeds,
                limit=limit,
            )[:, origin_pos]
            # distance from each attachment to every origin, plus its offset
            attached = (
                distances[seed_row]
                + part['offset_m'].to_numpy(
                    'float64',
                )[:, None]
            )
            # a destination's distance is the minimum over its attachments
            key_values = part['dest_key'].to_numpy()
            starts = np.flatnonzero(
                np.r_[True, key_values[1:] != key_values[:-1]],
            )
            reachable = np.minimum.reduceat(attached, starts, axis=0)
            reachable[:, ~origin_in_graph] = np.inf
            for band in bands:
                totals[band] += (reachable <= band).sum(axis=0)
        for band in bands:
            records.append(
                pd.DataFrame(
                    {
                        'osmid': origin_ids,
                        'spec': name,
                        'band': band,
                        'n': totals[band],
                    },
                ),
            )
    found = (
        pd.concat(records, ignore_index=True)
        if records
        else pd.DataFrame(columns=['osmid', 'spec', 'band', 'n'])
    )
    return _counts_frame(found, specs, bands, node_index, col_prefix)


def _nearest_distances_inmemory(
    r,
    specs,
    max_band,
    node_index,
    cost,
    reverse_cost,
    where,
    col_prefix,
    collect=None,
):
    """Exact per-origin nearest distance to each spec via in-memory Dijkstra (one pass).

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
        r,
        cost=cost,
        reverse_cost=reverse_cost,
        where=where,
    )
    n = graph.shape[0]
    dest = r.get_df(
        f'SELECT spec, dest_node, COALESCE(offset_m, 0)::float AS offset_m '
        f'FROM {_DEST_TABLE}',
    )
    # origin nodes absent from this pass's subgraph are unreachable (NaN row)
    origin_ids = node_index.to_numpy(dtype='int64')
    origin_pos = np.searchsorted(node_ids, origin_ids)
    origin_pos_clipped = np.clip(origin_pos, 0, n - 1)
    origin_in_graph = node_ids[origin_pos_clipped] == origin_ids

    origin_lookup = pd.Series(
        np.arange(len(origin_ids)),
        index=origin_ids,
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
            seed = (
                pd.DataFrame({'pos': seed_pos, 'off': seed_off})
                .groupby(
                    'pos',
                    as_index=False,
                )['off']
                .min()
            )
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
                    aug,
                    directed=True,
                    indices=n,
                    limit=limit,
                    return_predecessors=True,
                )
                dist = dist[:n]
                collect(name, dist, pred[:n], node_ids)
            dist[dist > max_band] = np.nan
            col = np.where(origin_in_graph, dist[origin_pos_clipped], np.nan)
        # identity co-location: a destination sharing an origin's network node is
        # reachable at its offset cost with no edge traversal, even where that node
        # has no edges in this pass's subgraph.  Matches pgr_drivingDistance,
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


AVOID = 'avoid'


def spec_name(column):
    """The destination spec a nearest-distance column belongs to.

    Every distance column is ``<prefix>nearest_node_<spec name>``, whatever the
    routing pass, so the spec is whatever follows the last 'nearest_node_'.
    Spec names may therefore not themselves contain 'nearest_node_'.
    """
    return column.split('nearest_node_')[-1]


def spec_thresholds(specs, thresholds):
    """Map each spec name to the distance bands its access is evaluated at.

    A spec may set its own ``distances`` where the policy-relevant threshold
    differs from the region's bands -- a petrol station judged at 250 m, say,
    against walking bands of 500 / 1000 / 1500 m.  Everything else uses the
    configured bands.
    """
    resolved = {}
    for s in specs:
        bands = s.get('distances') or thresholds
        resolved[s['name']] = tuple(sorted({int(d) for d in bands}))
    return resolved


def all_thresholds(specs, thresholds):
    """Every band any spec is evaluated at, ascending."""
    bands = {int(t) for t in thresholds}
    for s in specs:
        bands.update(int(d) for d in (s.get('distances') or ()))
    return tuple(sorted(bands))


def sample_point_access(
    r,
    nodes_poi_dist,
    node_index,
    thresholds,
    specs,
    config,
    access_prefixes,
    nodes_counts=None,
    diversity=None,
    diversity_prefixes=None,
):
    """Map node distances to sample points; derive per-spec and composite access.

    ``access_prefixes`` is the ordered list of 'access' column prefixes, one per
    routing pass (e.g. ``['sp_walk_access_']`` for the pedestrian analysis, or one
    per measure for cycling).  Distance columns are whatever ``nodes_poi_dist``
    carries; each is matched to its access columns by replacing 'nearest_node' with
    'access' and appending the threshold, so the two naming schemes stay in step.

    Two per-spec options are honoured.  ``distances`` restricts a spec to its own
    bands (see ``spec_thresholds``).  ``direction: avoid`` marks a spec as a
    disamenity -- proximity is the harm, not the benefit -- so its threshold
    columns are named ``<prefix>beyond_<name>_<d>m`` and score 1 where the nearest
    one is *further* than d metres (including where there is none within the
    largest band).  This is the spec-level counterpart of the
    ``greater_than_or_equal_to`` sample point analysis in indicators.yml, and it
    matters that the polarity is carried in the name: an avoided destination
    aggregates to "percentage of population living beyond d metres", which is not
    what an access column of the same value would mean.
    """
    sample_points = r.get_gdf('urban_sample_points')
    sample_points.columns = [
        'geometry' if x == 'geom' else x for x in sample_points.columns
    ]
    sample_points = sample_points.set_index('point_id')

    # estimate each sample point's distance from its two terminal nodes + offsets.
    # Counts, where any were measured, are carried as 'density statistics' rather
    # than as distances: create_full_nodes adds the offset to each distance and
    # takes the minimum over the two terminal nodes, which is right for a
    # distance and meaningless for a count.  As a density statistic a count is
    # instead proximity weighted between the two nodes, the same treatment
    # population and intersection density already receive.
    nodes_simple = (
        pd.DataFrame(index=node_index)
        if nodes_counts is None
        else nodes_counts
    )
    count_names = [] if nodes_counts is None else list(nodes_counts.columns)
    full_nodes = create_full_nodes(
        sample_points,
        nodes_simple,
        nodes_poi_dist,
        count_names,
    )
    sample_points = sample_points[
        ['grid_id', 'edge_ogc_fid', 'geometry']
    ].join(full_nodes, how='left')

    distance_names = list(nodes_poi_dist.columns)
    bands = spec_thresholds(specs, thresholds)
    avoided = {s['name'] for s in specs if s.get('direction') == AVOID}
    # Binary access per threshold.  Build all the access columns as standalone
    # frames and join them in one pd.concat rather than assigning column blocks
    # into the GeoDataFrame one threshold at a time: repeated insertion into a
    # frame that already holds 100+ columns fragments it, triggering pandas'
    # PerformanceWarning and O(ncols^2) recopying on large cities.
    access_frames = []
    for threshold in all_thresholds(specs, thresholds):
        applicable = [
            x
            for x in distance_names
            if threshold in bands.get(spec_name(x), ())
        ]
        if not applicable:
            continue
        scores = binary_access_score(sample_points, applicable, threshold)
        # binary_access_score returns the applicable columns in order; rename
        # positionally to the per-threshold access names (as the block assignment did)
        scores.columns = [
            f"{x.replace('nearest_node', 'access')}_{threshold}m"
            for x in applicable
        ]
        # an avoided destination reports the complement: 1 where the nearest is
        # further than the threshold, or absent within the largest band
        avoid_cols = [x for x in applicable if spec_name(x) in avoided]
        if avoid_cols:
            renamed = {}
            for x in avoid_cols:
                access = f"{x.replace('nearest_node', 'access')}_{threshold}m"
                beyond = f"{x.replace('nearest_node', 'beyond')}_{threshold}m"
                renamed[access] = beyond
                scores[access] = 1 - scores[access].fillna(0).astype(int)
            scores = scores.rename(columns=renamed)
        access_frames.append(scores)
    sample_points = pd.concat([sample_points] + access_frames, axis=1)

    # composite "all categories reachable" access, per named combined-access set and
    # strictness variant.  Each category contributes the spec matching the variant
    # (else its sole spec, so a single-variant custom category joins both).  The
    # 'standard' set keeps bare all_<variant> names for comparability; other sets are
    # namespaced all_<set>_<variant>.  Composites reference only per-spec access
    # columns (never other composites), so they are accumulated and concatenated once.
    sets = combined_access_sets(config, specs)
    axis = [
        v
        for v in ('strict', 'lenient')
        if any(s.get('variant') == v for s in specs)
    ]
    available = set(sample_points.columns)
    composites = {}
    for set_name, categories in sets.items():
        for variant in axis:
            members = [
                m
                for m in (
                    _resolve_member(specs, c, variant) for c in categories
                )
                if m is not None and m.get('direction') != AVOID
            ]
            names = [m['name'] for m in members]
            if len(names) < 2:
                continue
            infix = '' if set_name == STANDARD_SET else f'{set_name}_'
            # composites for every routing pass
            for measure in access_prefixes:
                for threshold in thresholds:
                    cols = [
                        f'{measure}{n}_{threshold}m'
                        for n in names
                        if f'{measure}{n}_{threshold}m' in available
                    ]
                    # every member must be present at this band: a partial
                    # composite would silently mean 'all of some categories'
                    if len(cols) == len(names):
                        col = f'{measure}all_{infix}{variant}_{threshold}m'
                        composites[col] = (
                            sample_points[cols]
                            .fillna(0)
                            .astype(int)
                            .prod(axis=1)
                        )
    if composites:
        sample_points = pd.concat(
            [
                sample_points,
                pd.DataFrame(composites, index=sample_points.index),
            ],
            axis=1,
        )

    # diversity of what is reachable, per configured set and band.  Derived from
    # the sample point counts rather than from the node counts so that the score
    # is consistent with the counts reported alongside it: the entropy of an
    # interpolated count, not an interpolation between two entropies.
    if diversity and diversity_prefixes:
        count_prefix, diversity_prefix, richness_prefix = diversity_prefixes
        diversity_scores = {}
        for set_name, definition in diversity.items():
            for band in set_bands(definition, thresholds):
                columns = [
                    count_column(
                        count_prefix,
                        f'{set_name}{DIVERSITY_GROUP_SEPARATOR}{group}',
                        band,
                    )
                    for group in definition['groups']
                ]
                # every group must have been counted at this band; a partial set
                # would silently be a diversity score over a different k
                if not all(c in sample_points.columns for c in columns):
                    continue
                counts = sample_points[columns]
                diversity_scores[f'{diversity_prefix}{set_name}_{band}m'] = (
                    normalised_entropy(counts)
                )
                diversity_scores[f'{richness_prefix}{set_name}_{band}m'] = (
                    richness(counts)
                )
        if diversity_scores:
            sample_points = pd.concat(
                [
                    sample_points,
                    pd.DataFrame(diversity_scores, index=sample_points.index),
                ],
                axis=1,
            )
    return sample_points
