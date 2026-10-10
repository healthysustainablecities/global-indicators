"""
Separating real-world change from OpenStreetMap mapping change in series.

Longitudinal comparisons of indicators derived from OpenStreetMap (OSM) can
reflect growth in mapping detail as well as real change.  Following the
completeness framework of Herfort et al. (2023, Nature Communications 14,
3985), this module assesses, for a series, how far change in OSM-derived
destinations reflects mapping rather than development (phase 1 of
process/osm_change_attribution_plan.md):

1. Provenance of OSM destinations between timepoints: each destination at
   a later timepoint is classed as persistent (the same OSM element in the
   same category earlier), newly classified (the OSM element existed
   earlier, as its identifier is no greater than the earlier extract's
   maximum for its element type, but was not in this category: re-tagged
   or given detail, i.e. mapping change) or newly created in OSM; earlier
   destinations absent later are removed.  An added destination within a
   short distance of a removed destination of the same category is a
   replacement (e.g. a shop re-mapped from a point to a building outline,
   or one shop succeeding another), neither growth nor loss in access.
   OSM identifiers are assigned in order of creation, so no editing
   history is required.
2. Evidence of real-world development, by grid cell: cells whose population
   grew by at least a configured amount (or became populated) are
   'developing'; others 'stable'.  Destinations newly created in OSM in
   stable cells are more likely mapping catch-up than new facilities.
3. Completeness of OSM public transport stops against GTFS stops at each
   timepoint: the share of GTFS stops with an OSM public transport feature
   within a configured distance.
4. Mapping change by socio-economic stratum (e.g. IRSD deciles held fixed
   at baseline): whether new OSM destinations concentrate in more or less
   advantaged areas.
5. Network detail: network length by highway class at each timepoint.
6. A strength of evidence summary for each indicator.

The pure functions (classify_provenance, flag_development,
provenance_summary, evidence_rating) take DataFrames and are unit tested;
the Series methods in longitudinal.py retrieve data from each timepoint's
database and call these.
"""

import re
import subprocess

import numpy as np
import pandas as pd

# destination categories underlying each OSM-derived indicator; indicators
# not listed are derived from other sources (GTFS, population, configured
# intersections) unless named in OSM_UNASSESSED
INDICATOR_DESTINATIONS = {
    'pct_access_500m_fresh_food_market_score': ['fresh_food_market'],
    'pct_access_500m_convenience_score': ['convenience'],
    'pct_access_500m_pt_osm_any_score': ['pt_any'],
    'local_daily_living': ['fresh_food_market', 'convenience'],
    'all_cities_walkability': ['fresh_food_market', 'convenience'],
}
# OSM-derived indicators whose provenance phase 1 does not assess
OSM_UNASSESSED = {
    'pct_access_500m_public_open_space_any_score': 'OSM open space areas',
    'pct_access_500m_public_open_space_large_score': 'OSM open space areas',
    'pct_access_500m_pt_any_score': 'GTFS and OSM public transport stops',
    'local_walkability': (
        'standardised within each timepoint, so not comparable over time; '
        'see all_cities_walkability'
    ),
}
NON_OSM_SOURCES = {
    'pct_access_500m_pt_gtfs_any_score': 'GTFS',
    'pct_access_500m_pt_gtfs_freq_30_score': 'GTFS',
    'pct_access_500m_pt_gtfs_freq_20_score': 'GTFS',
    'local_nh_population_density': 'population grid',
    'local_nh_intersection_density': 'configured intersections',
}
DEFAULTS = {
    'development': {'min_population_increase': 100},
    'pt_stops': {'distance_m': 50},
    'replacement': {'distance_m': 50},
    'evidence_thresholds': {'mapping_share': 0.25, 'uncertain_share': 0.5},
}
PROVENANCE_CLASSES = [
    'persistent',
    'newly_classified',
    'newly_created',
    'replaced',
    'removed',
    'replaced_earlier',
]


def pbf_max_ids(pbf: str) -> dict:
    """Return the maximum OSM node, way and relation identifiers in a .pbf."""
    output = subprocess.run(
        ['osmconvert', '--out-statistics', pbf],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    max_ids = {}
    for element in ('node', 'way', 'relation'):
        match = re.search(rf'^{element} id max: (\d+)', output, re.MULTILINE)
        max_ids[element] = int(match.group(1)) if match else None
    return max_ids


def classify_provenance(
    earlier: pd.DataFrame,
    later: pd.DataFrame,
    earlier_max_ids: dict,
    replacement_distance: float = None,
) -> pd.DataFrame:
    """
    Classify destinations by OSM provenance between two timepoints.

    earlier and later have columns osm_type ('node', 'way' or 'relation'),
    osm_id (integer, positive), category and grid_id (plus any others,
    kept).  earlier_max_ids gives the earlier extract's maximum identifier
    by element type.  Returns the later destinations classed 'persistent',
    'newly_classified' or 'newly_created', and the earlier destinations
    absent later classed 'removed', in a 'provenance' column.

    Given replacement_distance (and x, y coordinates in metres), each
    added destination nearest to a removed destination of the same
    category within that distance is classed 'replaced', and the removed
    destination it replaces 'replaced_earlier' (matched one to one,
    nearest pairs first).
    """
    key = ['osm_type', 'osm_id', 'category']
    earlier_keys = set(map(tuple, earlier[key].to_numpy()))
    later_keys = set(map(tuple, later[key].to_numpy()))
    later = later.copy()
    persistent = [tuple(k) in earlier_keys for k in later[key].to_numpy()]
    max_id = later['osm_type'].map(earlier_max_ids).astype('float64')
    existed = later['osm_id'].astype('float64') <= max_id
    later['provenance'] = np.select(
        [persistent, existed.to_numpy()],
        ['persistent', 'newly_classified'],
        default='newly_created',
    )
    removed = earlier[
        [tuple(k) not in later_keys for k in earlier[key].to_numpy()]
    ].copy()
    removed['provenance'] = 'removed'
    if replacement_distance:
        _match_replacements(later, removed, replacement_distance)
    return pd.concat([later, removed], ignore_index=True)


def _match_replacements(later, removed, distance):
    """Pair added and removed destinations of a category within distance."""
    from scipy.spatial import cKDTree

    added_mask = later['provenance'].isin(['newly_classified', 'newly_created'])
    for category in removed['category'].unique():
        old = removed[removed['category'] == category]
        new = later[added_mask & (later['category'] == category)]
        if old.empty or new.empty:
            continue
        tree = cKDTree(old[['x', 'y']].to_numpy())
        pairs = tree.sparse_distance_matrix(
            cKDTree(new[['x', 'y']].to_numpy()),
            distance,
            output_type='ndarray',
        )
        if len(pairs) == 0:
            continue
        pairs = np.sort(pairs, order='v')
        used_old, used_new = set(), set()
        for i, j, _ in pairs:
            if i in used_old or j in used_new:
                continue
            used_old.add(i)
            used_new.add(j)
        later.loc[new.index[list(used_new)], 'provenance'] = 'replaced'
        removed.loc[old.index[list(used_old)], 'provenance'] = 'replaced_earlier'


def flag_development(
    earlier: pd.DataFrame,
    later: pd.DataFrame,
    min_population_increase: float = 100,
) -> pd.DataFrame:
    """
    Flag grid cells as 'developing' or 'stable' between two timepoints.

    earlier and later have columns grid_id and pop_est.  A cell is
    developing where its population grew by at least
    min_population_increase, or it was unpopulated earlier and populated
    later.  Returns grid_id, pop_t0, pop_t1, pop_change and development.
    """
    cells = pd.merge(
        earlier[['grid_id', 'pop_est']].rename(columns={'pop_est': 'pop_t0'}),
        later[['grid_id', 'pop_est']].rename(columns={'pop_est': 'pop_t1'}),
        on='grid_id',
        how='outer',
    )
    cells[['pop_t0', 'pop_t1']] = cells[['pop_t0', 'pop_t1']].fillna(0)
    cells['pop_change'] = cells['pop_t1'] - cells['pop_t0']
    developing = (cells['pop_change'] >= min_population_increase) | (
        (cells['pop_t0'] <= 0) & (cells['pop_t1'] > 0)
    )
    cells['development'] = np.where(developing, 'developing', 'stable')
    return cells


def provenance_summary(provenance: pd.DataFrame) -> pd.DataFrame:
    """
    Summarise destination provenance by category.

    provenance has columns category, provenance and development (the later
    cell's development flag, 'developing', 'stable' or missing for cells
    outside the population grid).  Returns counts by provenance class,
    the net change, and the share of features added in the later
    timepoint (newly classified or newly created) that are likely mapping:
    newly classified, or newly created in stable cells.  Newly created
    features in developing cells are plausibly real; the likely mapping
    share is therefore an upper-bound estimate of mapping-driven growth,
    and newly classified share alone a lower bound.
    """
    rows = []
    for category, group in provenance.groupby('category'):
        counts = group['provenance'].value_counts()
        created = group[group['provenance'] == 'newly_created']
        created_stable = int((created['development'] == 'stable').sum())
        created_developing = int(
            (created['development'] == 'developing').sum(),
        )
        created_other = len(created) - created_stable - created_developing
        classified = int(counts.get('newly_classified', 0))
        replaced = int(counts.get('replaced', 0))
        added = classified + len(created)
        later_total = int(
            counts.get('persistent', 0) + classified + len(created) + replaced,
        )
        earlier_total = int(
            counts.get('persistent', 0)
            + counts.get('removed', 0)
            + counts.get('replaced_earlier', 0),
        )
        rows.append(
            {
                'category': category,
                'earlier_total': earlier_total,
                'later_total': later_total,
                'net_change': later_total - earlier_total,
                'persistent': int(counts.get('persistent', 0)),
                'replaced': replaced,
                'removed': int(counts.get('removed', 0)),
                'newly_classified': classified,
                'newly_created_stable': created_stable,
                'newly_created_developing': created_developing,
                'newly_created_unpopulated': created_other,
                'added': added,
                'mapping_share_lower': (
                    classified / added if added else np.nan
                ),
                'mapping_share_upper': (
                    (classified + created_stable) / added
                    if added
                    else np.nan
                ),
            },
        )
    return pd.DataFrame(rows)


def evidence_rating(
    indicator: str,
    summary: pd.DataFrame = None,
    stratum_ratio: float = None,
    thresholds: dict = None,
) -> dict:
    """
    Rate the strength of evidence for change in an indicator.

    Indicators from non-OSM sources are 'robust'.  For OSM destination
    indicators, the likely mapping share of added destinations (the upper
    estimate, see provenance_summary) across the indicator's categories
    is compared with thresholds: below mapping_share 'robust', from
    uncertain_share 'uncertain', otherwise 'moderate'.  A ratio of likely
    mapping additions per resident between the most and least advantaged
    strata beyond 1.5 (or below 1/1.5) is noted as differential mapping.
    Returns rating, source, mapping shares and reason.
    """
    thresholds = {**DEFAULTS['evidence_thresholds'], **(thresholds or {})}
    if indicator in NON_OSM_SOURCES:
        return {
            'indicator': indicator,
            'source': NON_OSM_SOURCES[indicator],
            'rating': 'robust',
            'reason': f'Not derived from OSM ({NON_OSM_SOURCES[indicator]}).',
        }
    if indicator in OSM_UNASSESSED:
        return {
            'indicator': indicator,
            'source': OSM_UNASSESSED[indicator],
            'rating': 'not assessed',
            'reason': (
                f'{OSM_UNASSESSED[indicator]}; provenance not assessed in '
                'phase 1.'
            ),
        }
    categories = INDICATOR_DESTINATIONS.get(indicator)
    if not categories or summary is None:
        return {
            'indicator': indicator,
            'source': 'unknown',
            'rating': 'not assessed',
            'reason': 'No provenance assessment configured.',
        }
    rows = summary[summary['category'].isin(categories)]
    added = rows['added'].sum()
    lower = rows['newly_classified'].sum() / added if added else np.nan
    upper = (
        (rows['newly_classified'].sum() + rows['newly_created_stable'].sum())
        / added
        if added
        else np.nan
    )
    if np.isnan(upper):
        rating = 'not assessed'
    elif upper < thresholds['mapping_share']:
        rating = 'robust'
    elif upper >= thresholds['uncertain_share']:
        rating = 'uncertain'
    else:
        rating = 'moderate'
    reason = (
        f'{added:,.0f} destinations added ({", ".join(categories)}); '
        f'{100 * lower:.0f}-{100 * upper:.0f}% likely mapping '
        '(newly classified; plus newly created in stable cells).'
    )
    if stratum_ratio is not None and np.isfinite(stratum_ratio):
        if stratum_ratio > 1.5 or stratum_ratio < 1 / 1.5:
            reason += (
                ' Likely mapping additions per resident differ by '
                f'socio-economic stratum (ratio {stratum_ratio:.2f}, most '
                'to least advantaged): change in gradients may partly '
                'reflect mapping.'
            )
    return {
        'indicator': indicator,
        'source': 'OSM destinations',
        'rating': rating,
        'mapping_share_lower': lower,
        'mapping_share_upper': upper,
        'reason': reason,
    }


def destinations_for_timepoint(region, area: tuple = None) -> pd.DataFrame:
    """
    Retrieve a timepoint's destinations with OSM element type and grid cell.

    Destinations compiled from the OSM point table are nodes; those from
    the polygon table (as centroids) are ways, or relations where osm2pgsql
    recorded a negative identifier.  Optionally, area (an aggregation name
    and its identifier column) assigns each destination an area_id.
    """
    prefix = region.config['osm_prefix']
    grid = region.config['population_grid']
    area_select, area_join = '', ''
    if area is not None:
        aggregation, id_column = area
        area_select = f', a."{id_column}" AS area_id'
        area_join = (
            f'LEFT JOIN agg_{aggregation} a ON ST_Intersects(a.geom, d.geom)'
        )
    sql = f"""
        SELECT d.osm_id::bigint AS osm_id,
               d.dest_name AS category,
               (p.osm_id IS NOT NULL) AS is_node,
               g.grid_id,
               ST_X(d.geom) AS x,
               ST_Y(d.geom) AS y
               {area_select}
        FROM destinations d
        LEFT JOIN {prefix}_point p
          ON p.osm_id = d.osm_id::bigint AND ST_Equals(p.geom, d.geom)
        LEFT JOIN {grid} g ON ST_Intersects(g.geom, d.geom)
        {area_join}
    """
    df = region.get_df(sql)
    df['osm_type'] = np.where(
        df['is_node'],
        'node',
        np.where(df['osm_id'] < 0, 'relation', 'way'),
    )
    df['osm_id'] = df['osm_id'].abs()
    return df.drop(columns='is_node').drop_duplicates(
        subset=['osm_type', 'osm_id', 'category'],
    )


def pt_stop_completeness_for_timepoint(region, distance_m: float = 50):
    """
    Share of GTFS stops with an OSM public transport feature nearby.

    Returns one row per GTFS stop location with its grid cell and whether
    an OSM public transport destination (pt_any) lies within distance_m.
    """
    grid = region.config['population_grid']
    sql = f"""
        SELECT s.stop_id, s.mode, g.grid_id,
               EXISTS (
                 SELECT 1 FROM destinations d
                 WHERE d.dest_name = 'pt_any'
                   AND ST_DWithin(d.geom, s.geom, {float(distance_m)})
               ) AS osm_matched
        FROM (SELECT DISTINCT ON (stop_id) stop_id, mode, geom
              FROM pt_stops_headway) s
        LEFT JOIN {grid} g ON ST_Intersects(g.geom, s.geom)
    """
    return region.get_df(sql)


def network_detail_for_timepoint(region) -> pd.DataFrame:
    """Network length (km) by OSM highway class for a timepoint."""
    df = region.get_df(
        'SELECT highway, SUM(length) / 1000 AS km FROM edges GROUP BY highway',
    )
    # multi-valued highway tags (e.g. ['footway', 'residential']) are
    # recorded as their first value
    df['highway'] = (
        df['highway']
        .astype(str)
        .str.strip("[]'\" ")
        .str.split("'")
        .str[0]
        .str.strip(", ")
    )
    return df.groupby('highway', as_index=False)['km'].sum()
