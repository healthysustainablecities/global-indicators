"""
Cycling Level of Traffic Stress (LTS) network.

Optional GHSCI analysis step, gated by the region configuration flag
``cycling_indicators: true``.  Classifies every routable edge in the ``edges`` table
with a Level of Traffic Stress (LTS 1-4) and an additive LTS impedance, following the
Global Cycling Indicators manuscript (LTS classification Table 1; two-component
impedance, section 2.2) and porting the prior R implementation.

Columns added to ``edges``:
    bike_facility    text   cycling infrastructure class
    maxspeed_kmh     float  parsed / imputed speed limit (km/h)
    adt              float  assumed average daily traffic (by road hierarchy)
    lvl_traf_stress  int    Level of Traffic Stress, 1 (low) to 4 (high)
    lts_imped        float  forward LTS impedance (m): link (length*(imped-1)) + 'to'-node
    cost_dist        float  geometric reachability cost: length (ridable), length*dismount
                            _weight (walked footway) -- the manuscript step-1 distance budget
    cost_lts         float  forward danger-weighted cost: length*danger (LTS3-4) + lts_imped;
                            walked footway = length*dismount_weight
    cost_lts_reverse float  as cost_lts but with the 'from'-node intersection penalty
    bike_permitted   bool   cycling permitted on the edge (ridable)
    foot_dismount    bool   walkable-but-not-ridable footway/path/pedestrian (LTS 1); routable
                            at the walked (dismount-weighted) cost

Directionality is intentionally ignored (the network is treated as undirected,
consistent with the GHSCI pgRouting accessibility engine); the R one-way edge
expansion and ADT halving are therefore omitted (the halving cancelled out in the R
LTS thresholds, so the LTS results are unchanged).

To run independently:  python subprocesses/_cycling_lts_network.py <codename>
"""

import os
import sys
import time

import ghsci
import numpy as np
import pandas as pd
from script_running_log import script_running_log
from sqlalchemy import text

# --- Methodology constants (manuscript Table 1; R addLTSAssumedTraffic.R) -----------

LOCAL = ['residential', 'road', 'unclassified', 'living_street', 'service']
TERTIARY = ['tertiary', 'tertiary_link']
SECONDARY = ['secondary', 'secondary_link']
PRIMARY = ['primary', 'primary_link']

# Off-road / non-motorised highway classes -> LTS 1 regardless of speed.
OFFROAD = ['cycleway', 'track', 'pedestrian', 'footway', 'path', 'corridor', 'steps']

# Assumed average daily traffic (ADT) by road hierarchy, as full two-way volumes.
ADT_BY_GROUP = {'local': 750.0, 'tertiary': 3000.0, 'secondary': 10000.0}

# Global default speed limits (km/h) by highway type, used where OSM ``maxspeed`` is
# missing.  Standard prototype mapping (mirrors cyclingIndicators/data/speed.csv);
# replace with a per-region ``hwy_speeds`` configuration block for published analyses
# (see GHSCI_INTEGRATION_PLAN.md section 5.2).
DEFAULT_SPEED_KMH = {
    'motorway': 100,
    'motorway_link': 80,
    'trunk': 80,
    'trunk_link': 70,
    'primary': 70,
    'primary_link': 55,
    'secondary': 55,
    'secondary_link': 50,
    'tertiary': 50,
    'tertiary_link': 40,
    'residential': 40,
    'road': 40,
    'unclassified': 40,
    'living_street': 30,
    'service': 25,
    'services': 25,
    'busway': 30,
    'bridleway': 20,
    'bus_stop': 25,
}

# Highway classes on which cycling is not permitted (prototype default; promote to a
# per-region configuration option to reflect local rules).
NO_CYCLE_DEFAULT = ['steps', 'corridor']

# ``motor_vehicle`` (or ``motorcar``) values that mean general through-traffic is not
# permitted -- the edge carries only local access (or no) motor traffic and so behaves
# as a low-stress local street regardless of its posted speed.  Following the manuscript
# and the prior R treatment, such edges are assigned a local speed cap and local ADT so
# they classify LTS 1-2 (e.g. an ``unclassified`` lane tagged ``motor_vehicle=destination``
# -> 30 km/h, LTS 1).  ``permissive`` / ``yes`` / ``designated`` are NOT restrictions.
MOTOR_RESTRICTED_VALUES = {
    'no', 'destination', 'private', 'customers', 'permit', 'delivery',
    'agricultural', 'forestry', 'agricultural;forestry', 'forestry;agricultural',
    'restricted',
}
MOTOR_LOCAL_SPEED_KMH = 30.0

# Per-LTS buffer distances (m) and impedance multipliers (Jafari et al.; manuscript
# section 2.2).  ``LTS_IMPED`` scales the intersection-crossing penalty by the crossing
# link's stress; the link-based stress of routing is carried by ``DANGER_WEIGHT`` below
# (matching the R reference's ``length_weighted``), not a separate per-link multiplier.
LTS_BUFFER = {1: 0.0, 2: 5.0, 3: 10.0, 4: 25.0}
LTS_IMPED = {1: 1.0, 2: 1.05, 3: 1.10, 4: 1.15}

# Danger weighting applied to the geometric length of higher-stress (LTS 3-4) links in
# the routing cost, following the manuscript (section 2.4) and the R reference: LTS 1-2
# cost = length + intersection impedance; LTS 3-4 cost = length * 1.25 + impedance.  This
# makes stressful links "effectively longer" so low-stress routes are preferred, while
# still allowing high-stress links where needed for connectivity.
DANGER_WEIGHT = 1.25

# Dismount weighting for walkable-but-not-ridable ways (footway / path / pedestrian; all
# LTS 1).  A rider may dismount and walk the bike along these to reach the network or a
# destination (e.g. a sample point or park entrance sitting on a footway), so rather than
# hard-excluding them (which strands such points) they are routable, with the *walked*
# distance counted toward the accessibility threshold.  The distance is scaled by
# ``dismount_weight`` to reflect that walking is slower than cycling: the default 3.0
# approximates walking (~5 km/h) against cycling (~15 km/h), so 1 m walked consumes ~3 m of
# the distance budget.  Configurable via ``cycling_indicators.dismount_weight`` (set to 1.0
# to count walked distance 1:1, e.g. for efficiency evaluation).  Efficiency is handled by
# the banded accessibility routing, not by a punitive weight or a hard distance cap.
DISMOUNT_WEIGHT = 3.0

# Highway classes that are not ridable but are walkable (dismount).  All classify as LTS 1
# (off-road).  ``steps`` and ``corridor`` are excluded -- impractical to walk a bike.
DISMOUNT_HIGHWAYS = ['footway', 'path', 'pedestrian']

# Highway value priority (highest capacity first) for resolving list-like OSM tags
# such as "['residential', 'service']" -> 'residential'.
HIGHWAY_PRIORITY = [
    'trunk', 'trunk_link', 'primary', 'primary_link', 'secondary',
    'secondary_link', 'tertiary', 'tertiary_link', 'unclassified', 'road',
    'residential', 'living_street', 'service', 'track', 'path',
    'pedestrian', 'footway', 'steps', 'corridor',
]


def cycling_config(r):
    """Return the region's cycling-indicators config dict, or None if disabled.

    ``cycling_indicators`` in the region YAML may be ``true`` (enabled with defaults),
    a mapping of options, or absent / ``false`` (disabled).
    """
    cfg = r.config.get('cycling_indicators')
    if cfg in (None, False):
        return None
    if cfg is True:
        return {}
    return cfg


def _data_path(path):
    """Resolve a config-relative data path under process/data."""
    return os.path.join(ghsci.folder_path, 'process', 'data', path)


def load_speed_defaults(speed_config):
    """Per-highway default speeds (km/h) from config, over the built-in table.

    A CSV (columns ``highway``, ``default_maxspeed``) if ``defaults_csv`` is set, or an
    inline ``defaults`` mapping, is layered **on top of** the built-in global defaults
    rather than replacing it.  This guarantees that highway classes the region omits
    (e.g. ``unclassified``, ``*_link``, ``busway``) still receive a sensible speed
    instead of falling through to NaN -> LTS 4.
    """
    speed_config = speed_config or {}
    defaults = dict(DEFAULT_SPEED_KMH)
    if speed_config.get('defaults_csv'):
        df = pd.read_csv(_data_path(speed_config['defaults_csv']))
        df['highway'] = df['highway'].astype(str).str.strip().str.lower()
        speeds = pd.to_numeric(df['default_maxspeed'], errors='coerce')
        defaults.update(dict(zip(df['highway'], speeds)))
    elif speed_config.get('defaults'):
        defaults.update({
            str(k).strip().lower(): v
            for k, v in speed_config['defaults'].items()
        })
    return defaults


def _zone_matched_edges(r, tmp, zone):
    """Return the set of edge ogc_fids matched to a (PostGIS) speed-zone geometry.

    ``overlap`` (default, R "bufferRatio"): an edge qualifies when at least
    ``overlap_threshold`` (default 0.5) of its buffered footprint (``edge_buffer`` m,
    default max(5, buffer/2)) lies within the zone.  ``intersects`` / ``within`` are
    the cruder ST_Intersects / ST_Within predicates.
    """
    method = zone.get('method', 'overlap')
    if method == 'overlap':
        buffer = zone.get('buffer')
        edge_buffer = zone.get('edge_buffer')
        if edge_buffer is None:
            edge_buffer = max(5.0, float(buffer) / 2.0) if buffer else 5.0
        threshold = float(zone.get('overlap_threshold', 0.5))
        sql = (
            f'SELECT e.ogc_fid FROM edges e JOIN {tmp} z '
            f'ON ST_Intersects(e.geom, z.geom) WHERE '
            f'ST_Area(ST_Intersection(ST_Buffer(e.geom, {edge_buffer}), z.geom)) '
            f'/ NULLIF(ST_Area(ST_Buffer(e.geom, {edge_buffer})), 0) >= {threshold}'
        )
    elif method == 'within':
        sql = (
            f'SELECT e.ogc_fid FROM edges e JOIN {tmp} z '
            f'ON ST_Within(e.geom, z.geom)'
        )
    else:
        sql = (
            f'SELECT e.ogc_fid FROM edges e JOIN {tmp} z '
            f'ON ST_Intersects(e.geom, z.geom)'
        )
    return set(r.get_df(sql)['ogc_fid'])


def apply_speed_zones(r, edges, zones):
    """Override edge speeds (km/h) for edges matched to configured speed zones.

    Ports the R assignBufferSpeed.  Each zone is a polygon or line dataset
    (geojson / gpkg) under process/data; lines are buffered into a polygon via the
    ``buffer`` (m) option and the zone is unioned before matching (see
    ``_zone_matched_edges`` for the ``overlap`` / ``intersects`` / ``within`` methods).

    By default only edges whose OSM ``maxspeed`` was missing are overridden
    (``apply_to: missing``, the R behaviour, preserving tagged speeds); set
    ``apply_to: all`` to override every matched edge.
    """
    import geopandas as gpd

    srid = r.config['crs']['srid']
    osm_missing = pd.Series(
        parse_speed_kmh(edges['maxspeed']), index=edges.index,
    ).isna()

    for i, zone in enumerate(zones):
        gdf = gpd.read_file(_data_path(zone['data']), layer=zone.get('layer'))
        gdf = gdf.to_crs(epsg=srid)
        if zone.get('buffer'):
            gdf['geometry'] = gdf.geometry.buffer(float(zone['buffer']))
        try:
            merged = gdf.geometry.union_all()
        except AttributeError:
            merged = gdf.geometry.unary_union
        zone_gdf = gpd.GeoDataFrame({'geom': [merged]}, geometry='geom', crs=gdf.crs)
        tmp = f'_cycle_speed_zone_{i}'
        with r.engine.connect() as conn:
            zone_gdf.to_postgis(tmp, conn, if_exists='replace', index=False)
        with r.engine.begin() as conn:
            conn.execute(text(f'CREATE INDEX ON {tmp} USING GIST (geom)'))

        matched = _zone_matched_edges(r, tmp, zone)
        with r.engine.begin() as conn:
            conn.execute(text(f'DROP TABLE IF EXISTS {tmp}'))

        mask = edges['ogc_fid'].isin(matched)
        if zone.get('apply_to', 'missing') == 'missing':
            mask = mask & osm_missing
        edges.loc[mask, 'maxspeed_kmh'] = float(zone['speed'])
        print(
            f'  - speed zone {i} ({zone["data"]}, method='
            f'{zone.get("method", "overlap")}, apply_to='
            f'{zone.get("apply_to", "missing")}): {int(mask.sum())} edges set '
            f'to {zone["speed"]} km/h',
        )
    return edges


def _lower(series):
    """Lower-case, strip and stringify a column, NaN-safe."""
    return series.astype('string').str.strip().str.lower()


def _pick_highway(value):
    """Resolve a (possibly list-like) OSM highway value to a single class.

    Mirrors R createCycleway: a ``cycleway`` value takes precedence; otherwise the
    highest-capacity class in a merged tag (e.g. "['residential', 'service']") is
    chosen by the priority order.
    """
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    text_value = str(value).strip().lower()
    if not text_value or text_value == '<na>':
        return None
    if text_value.startswith('['):
        tokens = [
            t.strip().strip("'\"")
            for t in text_value.strip('[]').split(',')
            if t.strip()
        ]
    else:
        tokens = [text_value]
    if 'cycleway' in tokens:
        return 'cycleway'
    ranked = [
        (HIGHWAY_PRIORITY.index(t) if t in HIGHWAY_PRIORITY else len(HIGHWAY_PRIORITY), t)
        for t in tokens
    ]
    return min(ranked)[1] if ranked else None


def parse_speed_kmh(series):
    """Parse an OSM ``maxspeed`` column to numeric km/h (handles mph and units)."""
    raw = series.astype('string').str.lower()
    number = raw.str.extract(r'(\d+\.?\d*)')[0].astype('float')
    is_mph = raw.str.contains('mph', na=False)
    return np.where(is_mph, number * 1.60934, number)


def _edge_columns(r):
    """Return the set of column names on the ``edges`` table."""
    sql = (
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'edges'"
    )
    return set(r.get_df(sql)['column_name'])


def load_edges(r):
    """Load the routable edge attributes needed for LTS classification."""
    available = _edge_columns(r)
    # tag columns may be absent or use OSM colon names (cycleway:left); select defensively
    wanted = {
        'highway': 'highway',
        'oneway': 'oneway',
        'bicycle': 'bicycle',
        'foot': 'foot',
        'access': 'access',
        'motor_vehicle': 'motor_vehicle',
        'cycleway': 'cycleway',
        'cycleway:left': 'cycleway_left',
        'cycleway_left': 'cycleway_left',
        'cycleway:right': 'cycleway_right',
        'cycleway_right': 'cycleway_right',
        'maxspeed': 'maxspeed',
    }
    select = ['ogc_fid', '"from"', '"to"', 'length']
    for col, alias in wanted.items():
        if col in available:
            select.append(f'"{col}" AS {alias}')
    sql = f'SELECT {", ".join(select)} FROM edges'
    edges = r.get_df(sql)
    # guarantee the optional columns exist downstream
    for alias in [
        'highway', 'oneway', 'bicycle', 'foot', 'access', 'motor_vehicle',
        'cycleway', 'cycleway_left', 'cycleway_right', 'maxspeed',
    ]:
        if alias not in edges.columns:
            edges[alias] = pd.NA
    # warn if the OSM cycle tags never made it onto the edges table: cycle-
    # infrastructure classification then falls back to highway type only
    missing = [
        a
        for a in [
            'cycleway', 'cycleway_left', 'cycleway_right', 'bicycle',
            'motor_vehicle', 'foot',
        ]
        if a not in edges.columns or edges[a].isna().all()
    ]
    if missing:
        print(
            f'  WARNING: cycle tags absent/empty on edges ({", ".join(missing)}). '
            'bike_facility will fall back to highway type only. Rebuild the network '
            'with the cycling-2025 _03_create_network_resources, which retains the '
            'OSM cycle tags.',
        )
    return edges


def classify_cycleway(edges):
    """Assign a cycling-infrastructure class (R createCycleway -> bike_facility)."""
    foot = _lower(edges['foot'])
    bicycle = _lower(edges['bicycle'])
    motor = _lower(edges['motor_vehicle'])
    cw = _lower(edges['cycleway'])
    cwl = _lower(edges['cycleway_left'])
    cwr = _lower(edges['cycleway_right'])

    highway = edges['highway'].map(_pick_highway)

    foot_no = foot.isin(['no', 'restricted', 'private'])
    bike_yes = bicycle.str.contains(
        r'\b(?:yes|designated|official)\b', na=False,
    )
    motor_no = motor.isin(['no', 'private'])

    def _any(pattern):
        return (
            cw.str.contains(pattern, na=False)
            | cwl.str.contains(pattern, na=False)
            | cwr.str.contains(pattern, na=False)
        )

    cw_track = _any(r'\btrack\b')
    cw_lane = _any(r'\blane\b')
    cw_shared = _any(r'\bshared_lane\b')
    is_cycleway = highway == 'cycleway'

    # sequential precedence, mirroring the R if_else cascade
    hierarchy = np.where(is_cycleway, 4, 0)
    hierarchy = np.where(cw_shared & ~is_cycleway, 1, hierarchy)
    hierarchy = np.where(cw_lane & ~is_cycleway, 2, hierarchy)
    hierarchy = np.where(cw_track & ~is_cycleway, 3, hierarchy)
    hierarchy = np.where(foot_no & is_cycleway, 5, hierarchy)
    hierarchy = np.where(motor_no & bike_yes & (hierarchy < 5), 4, hierarchy)

    facility = pd.Series('no lane/track/path', index=edges.index)
    facility = facility.mask(hierarchy == 1, 'shared_street')
    facility = facility.mask(hierarchy == 2, 'simple_lane')
    facility = facility.mask(hierarchy == 3, 'separated_lane')
    facility = facility.mask(hierarchy == 4, 'shared_path')
    facility = facility.mask(hierarchy == 5, 'bikepath')
    return highway, facility


def assign_speed(edges, defaults=None):
    """Parse OSM maxspeed to km/h, filling gaps with per-highway defaults.

    Edges with neither a parsed speed nor a default are left NaN, which falls through
    to LTS 4 in assign_lts (matching the R behaviour; off-road classes are LTS 1
    regardless of speed).
    """
    defaults = defaults or DEFAULT_SPEED_KMH
    speed = pd.Series(parse_speed_kmh(edges['maxspeed']), index=edges.index)
    default_speed = edges['highway'].map(defaults)
    return speed.fillna(default_speed).round()


def assign_adt(highway):
    """Assumed ADT by road hierarchy (NaN for classes without an assumption)."""
    adt = pd.Series(np.nan, index=highway.index)
    adt = adt.mask(highway.isin(LOCAL), ADT_BY_GROUP['local'])
    adt = adt.mask(highway.isin(TERTIARY), ADT_BY_GROUP['tertiary'])
    adt = adt.mask(highway.isin(SECONDARY), ADT_BY_GROUP['secondary'])
    return adt


def motor_restricted(series):
    """Boolean mask of edges whose ``motor_vehicle`` tag bars general through-traffic.

    Handles list-like (``"['no', 'destination']"``) and ``;``-separated multi-values:
    an edge qualifies if *any* of its values is a restriction (see
    ``MOTOR_RESTRICTED_VALUES``).
    """
    raw = series.astype('string').str.lower()

    def _restricted(value):
        if value is None or pd.isna(value):
            return False
        tokens = (
            str(value)
            .replace('[', ' ').replace(']', ' ')
            .replace("'", ' ').replace('"', ' ')
            .replace(';', ',')
            .split(',')
        )
        return any(t.strip() in MOTOR_RESTRICTED_VALUES for t in tokens)

    return raw.map(_restricted).fillna(False).astype(bool)


def apply_motor_restriction(edges, speed, adt):
    """Lower speed/ADT on motor-restricted (local-access-only) edges.

    Such edges carry little or no through motor traffic, so they behave as low-stress
    local streets: speed is capped at ``MOTOR_LOCAL_SPEED_KMH`` (also filling a missing
    speed) and ADT is set to the local floor.  Returns ``(speed, adt)``.
    """
    if 'motor_vehicle' not in edges.columns:
        return speed, adt
    mask = motor_restricted(edges['motor_vehicle']).to_numpy()
    if not mask.any():
        return speed, adt
    speed = speed.copy()
    adt = adt.copy()
    capped = np.minimum(speed.fillna(MOTOR_LOCAL_SPEED_KMH), MOTOR_LOCAL_SPEED_KMH)
    speed.loc[mask] = capped.loc[mask]
    local = pd.Series(ADT_BY_GROUP['local'], index=adt.index)
    adt.loc[mask] = np.minimum(adt.fillna(ADT_BY_GROUP['local']), local).loc[mask]
    print(f'  - motor_vehicle restriction (local access): {int(mask.sum())} edges')
    return speed, adt


def assign_lts(highway, facility, speed, adt):
    """Assign LTS 1-4 (manuscript Table 1; R addLTS cascade, first match wins)."""
    local_t_s = LOCAL + TERTIARY + SECONDARY
    conditions = [
        # LTS 1 -- off-road paths
        facility.isin(['bikepath', 'shared_path']),
        highway.isin(OFFROAD),
        # LTS 1 -- separated cycle lanes
        (facility == 'separated_lane') & (speed <= 50),
        # LTS 1 -- on-road cycle lanes
        (facility == 'simple_lane') & highway.isin(local_t_s)
        & (adt <= 10000) & (speed <= 30),
        # LTS 1 -- mixed traffic
        highway.isin(LOCAL) & (adt <= 2000) & (speed <= 30),
        # LTS 2 -- separated cycle lanes
        (facility == 'separated_lane') & (speed <= 60),
        # LTS 2 -- on-road cycle lanes
        (facility == 'simple_lane') & highway.isin(local_t_s)
        & (adt <= 10000) & (speed <= 50),
        (facility == 'simple_lane')
        & (highway.isin(PRIMARY) | (highway.isin(local_t_s) & (adt > 10000)))
        & (speed <= 40),
        # LTS 2 -- mixed traffic
        highway.isin(LOCAL) & (adt <= 750) & (speed <= 50),
        highway.isin(LOCAL) & (adt <= 2000) & (speed <= 40),
        highway.isin(LOCAL + TERTIARY) & (adt <= 3000) & (speed <= 30),
        # LTS 3 -- on-road cycle lanes
        (facility == 'simple_lane') & (speed <= 60),
        # LTS 3 -- mixed traffic
        highway.isin(LOCAL) & (adt <= 750) & (speed <= 60),
        highway.isin(LOCAL + TERTIARY) & (adt <= 3000) & (speed <= 50),
        (
            highway.isin(SECONDARY + PRIMARY)
            | (highway.isin(LOCAL + TERTIARY) & (adt > 3000))
        )
        & (speed <= 40),
    ]
    choices = [1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3]
    return pd.Series(
        np.select(conditions, choices, default=4), index=highway.index,
    ).astype(int)


def _intersection_penalty(node_ids, buffer_a, node_max_lts, node_highway):
    """Unsignalised-intersection penalty (m) for approaching the given nodes.

    Mirrors the R formula ``(I_b - I_a) * (imped_b - 1)`` for the highest-LTS link
    'b' meeting at the node; signalised (and only signalised) nodes add nothing.
    Untagged / NA nodes count as unsignalised and receive the penalty.
    """
    max_lts = node_ids.map(node_max_lts)
    buffer_b = max_lts.map(LTS_BUFFER)
    imped_b = max_lts.map(LTS_IMPED)
    node_type = _lower(node_ids.map(node_highway))
    signalised = (
        (node_type == 'traffic_signals').fillna(False).to_numpy(dtype=bool)
    )
    penalty = np.where(signalised, 0.0, (buffer_b - buffer_a) * (imped_b - 1.0))
    return np.nan_to_num(np.asarray(penalty, dtype='float'), nan=0.0)


def add_impedance(
    r, edges, danger_weight=DANGER_WEIGHT, dismount_weight=DISMOUNT_WEIGHT,
):
    """LTS impedance and the two routing-cost columns used by cycling accessibility.

    Follows the manuscript (sections 2.2, 2.4) and the R reference ``length_weighted``.
    Two costs are produced:

    * ``cost_dist`` -- geometric distance for the *reachability* threshold (manuscript
      step 1).  Ridable links cost their geometric length; walkable dismount links
      (``foot_dismount``) cost ``length * dismount_weight`` (the walked distance, penalised
      for the slower speed of walking).  No stress terms -- this is a pure distance budget.
    * ``cost_lts`` / ``cost_lts_reverse`` -- the LTS-adjusted (danger-weighted) cost for the
      benefit-of-the-doubt indicator: geometric length x ``danger_weight`` on LTS 3-4
      ridable links, plus the LTS impedance; dismount links take ``length * dismount_weight``
      (they are LTS 1, so no danger term).

    ``lts_imped`` (manuscript section 2.2) has two components restored here: a link-based
    penalty ``length * (imped_a - 1)`` from the segment's own LTS (higher stress -> larger),
    plus an intersection penalty for entering a higher-stress unsignalised node.  The
    intersection term is directional (depends on the node entered), so the forward cost uses
    the 'to' node and the reverse cost the 'from' node.

    ``danger_weight`` (default 1.25) and ``dismount_weight`` (default 3.0) are configurable
    per region.  Requires ``bike_permitted`` and ``foot_dismount`` already set on ``edges``.
    """
    # node-level maximum LTS across all incident edges (the crossing link 'b')
    stacked = pd.concat(
        [
            edges[['from', 'lvl_traf_stress']].rename(columns={'from': 'node'}),
            edges[['to', 'lvl_traf_stress']].rename(columns={'to': 'node'}),
        ],
    )
    node_max_lts = stacked.groupby('node')['lvl_traf_stress'].max()
    node_highway = r.get_df('SELECT osmid, highway FROM nodes').set_index(
        'osmid',
    )['highway']

    buffer_a = edges['lvl_traf_stress'].map(LTS_BUFFER)
    to_penalty = _intersection_penalty(
        edges['to'], buffer_a, node_max_lts, node_highway,
    )
    from_penalty = _intersection_penalty(
        edges['from'], buffer_a, node_max_lts, node_highway,
    )
    length = edges['length'].to_numpy()
    dismount = edges['foot_dismount'].fillna(False).to_numpy(dtype=bool)

    # section 2.2 link-based impedance component: length * (imped_a - 1) by the link's own
    # LTS (0% at LTS 1, 5/10/15% at LTS 2/3/4).  Zero on dismount links (LTS 1).
    imped_a = edges['lvl_traf_stress'].map(LTS_IMPED).to_numpy(dtype='float')
    link_imped = length * (imped_a - 1.0)

    # cost_dist: pure geometric distance for the reachability threshold; walked dismount
    # links penalised by dismount_weight.  Symmetric (no directional intersection term).
    edges['cost_dist'] = np.where(dismount, length * dismount_weight, length)

    # cost_lts: danger-weighted (LTS 3-4 ridable x danger_weight) + LTS impedance;
    # dismount links take length * dismount_weight (LTS 1 -> no danger term).
    base_danger = np.where(
        edges['lvl_traf_stress'].isin([3, 4]).to_numpy(), danger_weight, 1.0,
    )
    weighted_length = np.where(
        dismount, length * dismount_weight, length * base_danger,
    )
    edges['lts_imped'] = link_imped + to_penalty
    edges['cost_lts'] = weighted_length + link_imped + to_penalty
    edges['cost_lts_reverse'] = weighted_length + link_imped + from_penalty
    return edges


def assign_bike_permitted(edges, no_cycle=None):
    """Flag edges where cycling is permitted.

    An explicit ``bicycle`` permission (``yes`` / ``designated`` / ``official``)
    **overrides** the ``no_cycle`` highway-class ban -- a footway or path signed for
    cycling (a German shared cycle/foot path is the common case) is bikeable even though
    its base class is on the no-cycle list.  Cycling is barred only where ``bicycle`` is
    explicitly ``no`` / ``dismount`` / ``private``, or the class is on ``no_cycle`` and
    there is no explicit cycling permission.
    """
    no_cycle = no_cycle or NO_CYCLE_DEFAULT
    bicycle = _lower(edges['bicycle'])
    bike_no = bicycle.isin(['no', 'dismount', 'private'])
    bike_yes = bicycle.str.contains(
        r'\b(?:yes|designated|official)\b', na=False,
    )
    class_banned = edges['highway'].isin(no_cycle) & ~bike_yes
    return ~(bike_no | class_banned)


def compute_foot_dismount(edges):
    """Flag walkable-but-not-ridable ways the rider can dismount and walk along.

    A ``foot_dismount`` edge is a footway / path / pedestrian way (``DISMOUNT_HIGHWAYS``,
    all LTS 1) where cycling is **not** permitted but walking is -- i.e. not already
    ``bike_permitted`` and not barred to pedestrians (``foot`` / ``access`` not
    ``no`` / ``private``).  These are routable at a walked (dismount-weighted) cost so that
    sample points and destinations sitting on footways are not stranded; the walked
    distance is counted toward the accessibility threshold.  Unlike the earlier capped
    approach there is no distance limit here -- routing extent is bounded by the distance
    threshold and kept efficient by the banded accessibility routing.
    """
    permitted = edges['bike_permitted'].fillna(False).to_numpy(dtype=bool)
    is_dismount_class = edges['highway'].isin(DISMOUNT_HIGHWAYS).to_numpy()
    barred = _lower(edges['foot']).isin(['no', 'private']).to_numpy()
    if 'access' in edges.columns:
        barred = barred | _lower(edges['access']).isin(['no', 'private']).to_numpy()
    foot_dismount = pd.Series(
        (~permitted) & is_dismount_class & (~barred), index=edges.index,
    )
    print(
        f'  - foot dismount ways (walkable footway/path/pedestrian, not ridable): '
        f'{int(foot_dismount.sum())}',
    )
    return foot_dismount.fillna(False)


def write_back(r, edges):
    """Write the computed LTS columns back onto the edges table via a temp join."""
    out = edges[
        [
            'ogc_fid', 'bike_facility', 'maxspeed_kmh', 'adt',
            'lvl_traf_stress', 'lts_imped', 'cost_dist', 'cost_lts',
            'cost_lts_reverse', 'bike_permitted', 'foot_dismount',
        ]
    ].copy()
    out.to_sql('_cycling_lts', r.engine, if_exists='replace', index=False)
    statements = [
        'ALTER TABLE edges ADD COLUMN IF NOT EXISTS bike_facility text',
        'ALTER TABLE edges ADD COLUMN IF NOT EXISTS maxspeed_kmh double precision',
        'ALTER TABLE edges ADD COLUMN IF NOT EXISTS adt double precision',
        'ALTER TABLE edges ADD COLUMN IF NOT EXISTS lvl_traf_stress integer',
        'ALTER TABLE edges ADD COLUMN IF NOT EXISTS lts_imped double precision',
        'ALTER TABLE edges ADD COLUMN IF NOT EXISTS cost_dist double precision',
        'ALTER TABLE edges ADD COLUMN IF NOT EXISTS cost_lts double precision',
        'ALTER TABLE edges ADD COLUMN IF NOT EXISTS cost_lts_reverse '
        'double precision',
        'ALTER TABLE edges ADD COLUMN IF NOT EXISTS bike_permitted boolean',
        'ALTER TABLE edges ADD COLUMN IF NOT EXISTS foot_dismount boolean',
        """
        UPDATE edges e SET
            bike_facility = t.bike_facility,
            maxspeed_kmh = t.maxspeed_kmh,
            adt = t.adt,
            lvl_traf_stress = t.lvl_traf_stress,
            lts_imped = t.lts_imped,
            cost_dist = t.cost_dist,
            cost_lts = t.cost_lts,
            cost_lts_reverse = t.cost_lts_reverse,
            bike_permitted = t.bike_permitted,
            foot_dismount = t.foot_dismount
        FROM _cycling_lts t WHERE e.ogc_fid = t.ogc_fid
        """,
        'CREATE INDEX IF NOT EXISTS edges_lvl_traf_stress_idx '
        'ON edges (lvl_traf_stress)',
        'DROP TABLE IF EXISTS _cycling_lts',
    ]
    with r.engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def compute_cycling_lts(r, config=None):
    """Classify LTS for all routable edges and write the results to the database."""
    config = config or {}
    speed_config = config.get('speed_limits', {})
    defaults = load_speed_defaults(speed_config)
    no_cycle = config.get('no_cycle', NO_CYCLE_DEFAULT)
    danger_weight = float(config.get('danger_weight', DANGER_WEIGHT))
    dismount_weight = float(config.get('dismount_weight', DISMOUNT_WEIGHT))

    print('  - Loading routable edges...')
    edges = load_edges(r)
    print(f'  - Classifying LTS for {len(edges)} edges...')
    highway, facility = classify_cycleway(edges)
    edges['highway'] = highway
    edges['bike_facility'] = facility
    edges['maxspeed_kmh'] = assign_speed(edges, defaults)
    if speed_config.get('zones'):
        edges = apply_speed_zones(r, edges, speed_config['zones'])
    edges['adt'] = assign_adt(edges['highway'])
    # local-access-only edges (motor_vehicle=destination/private/no/...) behave as
    # low-stress local streets: cap speed and ADT before LTS classification
    edges['maxspeed_kmh'], edges['adt'] = apply_motor_restriction(
        edges, edges['maxspeed_kmh'], edges['adt'],
    )
    edges['lvl_traf_stress'] = assign_lts(
        edges['highway'], edges['bike_facility'],
        edges['maxspeed_kmh'], edges['adt'],
    )
    # off-road classes are LTS 1 irrespective of speed; only a *non*-off-road edge with
    # no speed is forced to LTS 4 by the missing value, so warn on exactly those
    forced_lts4 = (
        edges['maxspeed_kmh'].isna()
        & (edges['lvl_traf_stress'] == 4)
        & ~edges['highway'].isin(OFFROAD)
    )
    if int(forced_lts4.sum()):
        unknown = sorted(edges.loc[forced_lts4, 'highway'].dropna().unique())
        print(
            f'  - WARNING: {int(forced_lts4.sum())} non-off-road edges have no speed '
            f'and so default to LTS 4; classes without a default: {unknown}',
        )
    # bike_permitted and foot_dismount must precede add_impedance: walkable non-ridable
    # ways take the dismount weighting in the routing cost rather than being excluded
    edges['bike_permitted'] = assign_bike_permitted(edges, no_cycle)
    edges['foot_dismount'] = compute_foot_dismount(edges)
    edges = add_impedance(
        r, edges, danger_weight=danger_weight, dismount_weight=dismount_weight,
    )
    print('  - Writing LTS attributes back to edges...')
    write_back(r, edges)
    summary = (
        edges['lvl_traf_stress'].value_counts().sort_index().to_dict()
    )
    print(f'  - LTS edge counts (1-4): {summary}')


def cycling_lts_network(codename):
    start = time.time()
    script = '_cycling_lts_network'
    task = 'Classify cycling Level of Traffic Stress for the routable network'
    r = ghsci.Region(codename)
    config = cycling_config(r)
    if config is None:
        print(
            'cycling_indicators is not enabled for this region; '
            'skipping LTS network.',
        )
        return
    if 'edges' not in r.tables:
        sys.exit(
            'The edges table was not found; run _03_create_network_resources first.',
        )
    print('\nClassifying cycling Level of Traffic Stress...')
    compute_cycling_lts(r, config)
    script_running_log(r.config, script, task, start)
    r.engine.dispose()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    cycling_lts_network(codename)


if __name__ == '__main__':
    main()
