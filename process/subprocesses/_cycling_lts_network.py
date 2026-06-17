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
    lts_imped        float  LTS impedance (m), added to length for safe routing
    cost_lts         float  length + lts_imped (safe-routing cost)
    bike_permitted   bool   whether cycling is permitted on the edge

Directionality is intentionally ignored (the network is treated as undirected,
consistent with the GHSCI pgRouting accessibility engine); the R one-way edge
expansion and ADT halving are therefore omitted (the halving cancelled out in the R
LTS thresholds, so the LTS results are unchanged).

To run independently:  python subprocesses/_cycling_lts_network.py <codename>
"""

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
}
SPEED_FALLBACK_KMH = 50.0

# Highway classes on which cycling is not permitted (prototype default; promote to a
# per-region configuration option to reflect local rules).
NO_CYCLE_DEFAULT = ['steps', 'corridor']

# Per-LTS buffer distances (m) and impedance multipliers (Jafari et al.; manuscript
# section 2.2).  Impedance has two components: a link term from the segment's own LTS,
# plus an intersection term for entering a higher-stress unsignalised intersection.
LTS_BUFFER = {1: 0.0, 2: 5.0, 3: 10.0, 4: 25.0}
LTS_IMPED = {1: 1.0, 2: 1.05, 3: 1.10, 4: 1.15}

# Highway value priority (highest capacity first) for resolving list-like OSM tags
# such as "['residential', 'service']" -> 'residential'.
HIGHWAY_PRIORITY = [
    'trunk', 'trunk_link', 'primary', 'primary_link', 'secondary',
    'secondary_link', 'tertiary', 'tertiary_link', 'unclassified', 'road',
    'residential', 'living_street', 'service', 'track', 'cycleway', 'path',
    'pedestrian', 'footway', 'steps', 'corridor',
]


def _lower(series):
    """Lower-case, strip and stringify a column, NaN-safe."""
    return series.astype('string').str.strip().str.lower()


def _pick_highway(value):
    """Resolve a (possibly list-like) OSM highway value to a single class by priority."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    text_value = str(value).strip().lower()
    if text_value.startswith('['):
        tokens = [
            t.strip().strip("'\"")
            for t in text_value.strip('[]').split(',')
            if t.strip()
        ]
    else:
        tokens = [text_value]
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
        'highway', 'oneway', 'bicycle', 'foot', 'motor_vehicle',
        'cycleway', 'cycleway_left', 'cycleway_right', 'maxspeed',
    ]:
        if alias not in edges.columns:
            edges[alias] = pd.NA
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
    # any explicit cycleway highway tag normalises to 'cycleway'
    highway = highway.where(~highway.fillna('').str.contains('cycleway'), 'cycleway')

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


def assign_speed(edges, defaults=None, fallback=SPEED_FALLBACK_KMH):
    """Parse OSM maxspeed to km/h, filling gaps with per-highway defaults."""
    defaults = defaults or DEFAULT_SPEED_KMH
    speed = pd.Series(parse_speed_kmh(edges['maxspeed']), index=edges.index)
    default_speed = edges['highway'].map(defaults)
    return speed.fillna(default_speed).fillna(fallback).round()


def assign_adt(highway):
    """Assumed ADT by road hierarchy (NaN for classes without an assumption)."""
    adt = pd.Series(np.nan, index=highway.index)
    adt = adt.mask(highway.isin(LOCAL), ADT_BY_GROUP['local'])
    adt = adt.mask(highway.isin(TERTIARY), ADT_BY_GROUP['tertiary'])
    adt = adt.mask(highway.isin(SECONDARY), ADT_BY_GROUP['secondary'])
    return adt


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


def add_impedance(r, edges):
    """Two-component LTS impedance and safe-routing cost (manuscript section 2.2)."""
    # node-level maximum LTS across all incident edges (the crossing link 'b')
    stacked = pd.concat(
        [
            edges[['from', 'lvl_traf_stress']].rename(columns={'from': 'node'}),
            edges[['to', 'lvl_traf_stress']].rename(columns={'to': 'node'}),
        ],
    )
    node_max_lts = stacked.groupby('node')['lvl_traf_stress'].max()

    # node highway type, to detect signalised intersections
    nodes = r.get_df('SELECT osmid, highway FROM nodes')
    node_highway = nodes.set_index('osmid')['highway']

    buffer_a = edges['lvl_traf_stress'].map(LTS_BUFFER)
    imped_a = edges['lvl_traf_stress'].map(LTS_IMPED)
    to_max_lts = edges['to'].map(node_max_lts)
    buffer_b = to_max_lts.map(LTS_BUFFER)
    imped_b = to_max_lts.map(LTS_IMPED)

    to_highway = _lower(edges['to'].map(node_highway))
    # nullable boolean -> plain bool; untagged / NA nodes count as unsignalised
    signalised = (
        (to_highway == 'traffic_signals').fillna(False).to_numpy(dtype=bool)
    )
    # unsignalised (incl. untagged nodes) receive the intersection penalty
    intersec = np.where(
        signalised, 0.0, (buffer_b - buffer_a) * (imped_b - 1.0),
    )
    # the link-based term is always defined (LTS in 1-4); only the intersection
    # term can be NaN (e.g. an isolated 'to' node), so default that to zero
    intersec = np.nan_to_num(np.asarray(intersec, dtype='float'), nan=0.0)
    lts_imped = (edges['length'] * (imped_a - 1.0)) + intersec
    edges['lts_imped'] = lts_imped.fillna(0.0)
    edges['cost_lts'] = edges['length'] + edges['lts_imped']
    return edges


def assign_bike_permitted(edges, no_cycle=None):
    """Flag edges where cycling is permitted (not bicycle=no, not a no-cycle class)."""
    no_cycle = no_cycle or NO_CYCLE_DEFAULT
    bicycle = _lower(edges['bicycle'])
    bike_no = bicycle.isin(['no', 'dismount', 'private'])
    return ~(bike_no | edges['highway'].isin(no_cycle))


def write_back(r, edges):
    """Write the computed LTS columns back onto the edges table via a temp join."""
    out = edges[
        [
            'ogc_fid', 'bike_facility', 'maxspeed_kmh', 'adt',
            'lvl_traf_stress', 'lts_imped', 'cost_lts', 'bike_permitted',
        ]
    ].copy()
    out.to_sql('_cycling_lts', r.engine, if_exists='replace', index=False)
    statements = [
        'ALTER TABLE edges ADD COLUMN IF NOT EXISTS bike_facility text',
        'ALTER TABLE edges ADD COLUMN IF NOT EXISTS maxspeed_kmh double precision',
        'ALTER TABLE edges ADD COLUMN IF NOT EXISTS adt double precision',
        'ALTER TABLE edges ADD COLUMN IF NOT EXISTS lvl_traf_stress integer',
        'ALTER TABLE edges ADD COLUMN IF NOT EXISTS lts_imped double precision',
        'ALTER TABLE edges ADD COLUMN IF NOT EXISTS cost_lts double precision',
        'ALTER TABLE edges ADD COLUMN IF NOT EXISTS bike_permitted boolean',
        """
        UPDATE edges e SET
            bike_facility = t.bike_facility,
            maxspeed_kmh = t.maxspeed_kmh,
            adt = t.adt,
            lvl_traf_stress = t.lvl_traf_stress,
            lts_imped = t.lts_imped,
            cost_lts = t.cost_lts,
            bike_permitted = t.bike_permitted
        FROM _cycling_lts t WHERE e.ogc_fid = t.ogc_fid
        """,
        'CREATE INDEX IF NOT EXISTS edges_lvl_traf_stress_idx '
        'ON edges (lvl_traf_stress)',
        'DROP TABLE IF EXISTS _cycling_lts',
    ]
    with r.engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def compute_cycling_lts(r):
    """Classify LTS for all routable edges and write the results to the database."""
    print('  - Loading routable edges...')
    edges = load_edges(r)
    print(f'  - Classifying LTS for {len(edges)} edges...')
    highway, facility = classify_cycleway(edges)
    edges['highway'] = highway
    edges['bike_facility'] = facility
    edges['maxspeed_kmh'] = assign_speed(edges)
    edges['adt'] = assign_adt(edges['highway'])
    edges['lvl_traf_stress'] = assign_lts(
        edges['highway'], edges['bike_facility'],
        edges['maxspeed_kmh'], edges['adt'],
    )
    edges = add_impedance(r, edges)
    edges['bike_permitted'] = assign_bike_permitted(edges)
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
    r.config['cycling_indicators'] = True
    if not r.config.get('cycling_indicators'):
        print(
            'cycling_indicators is not enabled for this region; skipping LTS network.',
        )
        return
    if 'edges' not in r.tables:
        sys.exit(
            'The edges table was not found; run _03_create_network_resources first.',
        )
    print('\nClassifying cycling Level of Traffic Stress...')
    compute_cycling_lts(r)
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
