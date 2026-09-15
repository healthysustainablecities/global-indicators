"""Export cycling-validation map layers from a region database to GeoJSONSeq.

Produces the per-layer newline-delimited GeoJSON inputs for building a single
<slug>.pmtiles vector-tile archive per city (via tippecanoe, run separately),
for the round-2 interactive validation site.

Layers exported (EPSG:4326):
    lts          edges with an LTS rating + popup attributes
    grid         100m indicators grid, headline cycling access + distance columns
    destinations point destinations (dest_name / dest_name_full)
    pos_any      public open space entry lines (any), + aos_ha (open space size)
    pos_large    public open space entry lines (large), + aos_ha
    ac_local     local activity centre clusters
    ac_complete  complete activity centre clusters
    boundary     urban study region
    buffer       buffered urban study region (the ~5000m analysis buffer)

Usage (inside the ghsci container):
    /env/bin/python subprocesses/_export_validation_tiles.py "data/Cycling/Würzburg/Würzburg.yml" [outdir]

Default outdir is /tmp/validation_tiles/<slug>/ (copy out with docker cp).
A manifest.json is written alongside the layer files with bbox, feature counts
and the layer list, for consumption by the tile build script and the site.
"""

import json
import os
import sys

if __name__ == '__main__':
    # usage examples give configuration paths relative to the process
    # folder; as a module this leaves the caller's directory alone
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ghsci  # noqa: E402
import numpy as np  # noqa: E402

from _accessibility_spec import (  # noqa: E402
    DEFAULT_DESTINATIONS,
    _resolve_member,
    accessibility_config,
    activity_centre_definitions,
    combined_access_sets,
    custom_indicators,
    effective_config,
    usable_destination_specs,
)

# slugify is shared with _cycling_validation_report
from _utils import slugify  # noqa: E402

# Grid measure families ('' = danger-weighted, 'safe_' = fully low-stress LTS 1-2
# route, 'lts1_' = LTS 1 only, 'ride_' = low-stress ridden throughout, no dismount)
# x destination categories x distance thresholds.  'dmgap_' is not a routed measure
# but the paired safe_-vs-ride_ contrast: the percentage of a cell's sample points
# whose access exists only because the rider may dismount and walk, plus (under its
# own avg_cycle_extra_ prefix) the mean extra riding distance needed to avoid it.
# Only columns that exist in the region database are exported; the viewer reads
# manifest.json grid_columns to know which permutations a city supports.
GRID_FAMILIES = ['', 'safe_', 'lts1_', 'ride_']
DMGAP_FAMILY = 'dmgap_'
GRID_CATEGORIES = [
    'fresh_food_market',
    'fresh_food_pooled',
    'pt_any',
    'pt_frequent',
    'public_open_space_any',
    'public_open_space_large',
    'activity_centre_local',
    'activity_centre_complete',
    'all_strict',
    'all_lenient',
]
GRID_DISTANCES = ['500m', '1000m', '2000m', '5000m']

# Only the destination points the cycling indicators actually reference.
INDICATOR_DEST_NAMES = ('fresh_food_market', 'convenience', 'pt_any')

EDGE_COLUMNS = [
    'osmid',
    'name',
    'highway',
    'maxspeed_kmh',
    'adt',
    'bike_facility',
    'lvl_traf_stress',
    'bike_permitted',
    'foot_dismount',
    'length',
]


def existing_columns(r, table):
    return set(
        r.get_df(
            f"""SELECT column_name FROM information_schema.columns
                WHERE table_schema='public' AND table_name='{table}'""",
        )['column_name'],
    )


def write_layer(gdf, path):
    gdf = gdf.to_crs(4326)
    try:
        gdf.to_file(path, driver='GeoJSONSeq', COORDINATE_PRECISION=6)
    except Exception:
        gdf.to_file(path, driver='GeoJSONSeq')
    return len(gdf)


def population_centre(r):
    """Population-weighted centre of the indicator grid as [lng, lat], or None."""
    srid = int(r.config['crs']['srid'])
    centre = r.get_gdf(
        f"""SELECT ST_SetSRID(ST_MakePoint(
                   SUM(ST_X(ST_Centroid(geom)) * pop_est) / SUM(pop_est),
                   SUM(ST_Y(ST_Centroid(geom)) * pop_est) / SUM(pop_est)),
                   {srid}) AS geom
            FROM indicators_100m_2025
            WHERE pop_est > 0""",
    )
    if centre.empty or centre.geometry.iloc[0] is None:
        return None
    point = centre.to_crs(4326).geometry.iloc[0]
    return [round(float(point.x), 5), round(float(point.y), 5)]


def grid_columns(r, categories=GRID_CATEGORIES):
    available = existing_columns(r, 'indicators_100m_2025')
    cols = []
    for fam in GRID_FAMILIES:
        for cat in categories:
            for dist in GRID_DISTANCES:
                cols.append(f'pct_access_cycle_{fam}{cat}_{dist}')
        for cat in categories:
            cols.append(f'avg_cycle_dist_{fam}{cat}')
    for cat in categories:
        for dist in GRID_DISTANCES:
            cols.append(f'pct_access_cycle_{DMGAP_FAMILY}{cat}_{dist}')
        cols.append(f'avg_cycle_extra_{DMGAP_FAMILY}{cat}')
    return [c for c in cols if c in available]


def city_profile(r):
    """Study-region size and network composition, for grouping cities.

    ``lts_share`` follows the validation report's LTS table (``lts_network`` and
    ``edge_categories`` in _cycling_validation_report.py): each category's km as a
    share of the whole routable network -- rideable links by LTS class, walk-only
    footways as ``dismount``, everything else ``excluded``.  A rideable link with no
    LTS class stays in the denominator without a category, as in the report.
    """
    region = r.get_df(
        'SELECT SUM(area_sqkm) AS area_sqkm, SUM(pop_est) AS pop_est '
        'FROM urban_study_region',
    ).iloc[0]
    network = r.get_df(
        """SELECT CASE
                    WHEN bike_permitted IS TRUE
                      THEN ROUND(lvl_traf_stress::numeric)::int::text
                    WHEN foot_dismount IS TRUE THEN 'dismount'
                    ELSE 'excluded'
                  END AS category,
                  SUM(length) / 1000.0 AS km
           FROM edges GROUP BY 1""",
    )
    total = float(network['km'].sum())
    km = dict(zip(network['category'], network['km'].astype(float)))
    return {
        'area_sqkm': round(float(region['area_sqkm']), 1),
        'pop_est': int(round(float(region['pop_est']))),
        'network_km': round(total, 1),
        'lts_share': {
            cat: round(100 * km.get(cat, 0.0) / total, 2) if total else None
            for cat in ('1', '2', '3', '4', 'dismount', 'excluded')
        },
    }


def add_custom_members(r, config, custom):
    """Record the destinations each custom composite requires, per variant.

    Combined-access sets and activity-centre definitions are lists of categories.
    Which destination stands in for a category depends on the variant and on the
    layers the region has (with no GTFS feed the strict public transport member is
    any stop), so members are resolved from the usable specs as the analysis does.
    The dashboard names these destinations rather than a 'strict'/'lenient' label.
    """
    specs = usable_destination_specs(
        r,
        list(config.get('destinations') or DEFAULT_DESTINATIONS),
    )
    sets = combined_access_sets(config, specs)
    centres = activity_centre_definitions(config)
    for ind in custom:
        if ind['kind'] == 'combined_access':
            categories = sets.get(ind['name'][len('all_'):])
        elif ind['kind'] == 'activity_centre':
            categories = (
                centres.get(ind['name'][len('activity_centre_'):]) or {}
            ).get('categories')
        else:
            continue
        if categories:
            ind['members'] = {
                v: [
                    m['name']
                    for m in (_resolve_member(specs, c, v) for c in categories)
                    if m
                ]
                for v in ('strict', 'lenient')
            }


def export(codename, outdir=None):
    r = ghsci.Region(codename)
    # site_slug/site_label (cycling_indicators.validation) let companion
    # configs sharing a region name (e.g. a custom-data sensitivity run)
    # publish under their own slug instead of overwriting the original city.
    cycling = r.config.get('cycling_indicators') or {}
    validation = (
        cycling.get('validation') if isinstance(cycling, dict) else None
    ) or {}
    slug = validation.get('site_slug') or slugify(r.name)
    label = validation.get('site_label') or r.name
    # the region's own measures (custom destinations, combined-access sets and
    # activity-centre definitions) join the standard grid categories
    access_config = effective_config(
        accessibility_config(r),
        cycling if isinstance(cycling, dict) else {},
    )
    custom = custom_indicators(access_config)
    add_custom_members(r, access_config, custom)
    categories = list(
        dict.fromkeys(
            GRID_CATEGORIES
            + [v['name'] for ind in custom for v in ind['variants'].values()],
        ),
    )
    outdir = outdir or f'/tmp/validation_tiles/{slug}'
    os.makedirs(outdir, exist_ok=True)
    manifest = {
        'name': label,
        'codename': codename,
        'slug': slug,
        'layers': {},
    }

    def record(layer, gdf):
        n = write_layer(gdf, f'{outdir}/{layer}.geojsonl')
        manifest['layers'][layer] = {
            'file': f'{layer}.geojsonl',
            'features': n,
        }
        print(f'  {layer}: {n} features', flush=True)

    print(f'{r.name} -> {outdir}', flush=True)

    edge_cols = [c for c in EDGE_COLUMNS if c in existing_columns(r, 'edges')]
    lts = r.get_gdf(
        f"""SELECT {', '.join(edge_cols)},
                   ROUND(length::numeric) AS length_m, geom
            FROM edges WHERE lvl_traf_stress IS NOT NULL""",
    ).drop(columns=['length'], errors='ignore')
    record('lts', lts)

    g_cols = grid_columns(r, categories)
    # integer values (pct 0-100, distances in m): halves tile size via value dedup
    rounded = ', '.join(f'ROUND({c}::numeric)::int AS {c}' for c in g_cols)
    record(
        'grid',
        r.get_gdf(f'SELECT {rounded}, geom FROM indicators_100m_2025'),
    )

    # links riders must dismount and walk, scored by the population routed over them
    if 'cycling_dismount_priority' in r.tables:
        record(
            'dismount',
            r.get_gdf(
                """SELECT osmid, name, highway,
                          ROUND(length::numeric) AS length_m,
                          ROUND(dm_pop_served::numeric)::int AS dm_pop_served,
                          ROUND(dm_pop_dependent::numeric)::int AS dm_pop_dependent,
                          dm_specs, geom
                   FROM cycling_dismount_priority
                   WHERE dm_pop_served >= 1""",
            ),
        )

    record(
        'destinations',
        r.get_gdf(
            f"""SELECT dest_name, dest_name_full, geom FROM destinations
                WHERE dest_name IN {INDICATOR_DEST_NAMES}""",
        ),
    )
    # destinations of the region's own measures (e.g. bike racks, lake shores, custom
    # activity centres), tagged by the indicator they serve; lines and polygons are
    # reduced to a point so the dashboard can draw every overlay as circles
    overlay_sql = []
    for ind in custom:
        for name, o in ind['overlays'].items():
            if o['layer'] not in r.tables:
                continue
            where = f' WHERE {o["where"]}' if o['where'] else ''
            overlay_sql.append(
                f"""SELECT '{name}'::text AS ind, ST_PointOnSurface(geom) AS geom
                    FROM "{o['layer']}"{where}""",
            )
    if overlay_sql:
        record('custom_dest', r.get_gdf(' UNION ALL '.join(overlay_sql)))
    if 'pt_stops_headway' in r.tables:
        record(
            'pt_frequent',
            r.get_gdf(
                """SELECT stop_name, mode, headway, geom
                   FROM pt_stops_headway WHERE headway <= 20""",
            ),
        )
    for layer, table in [
        ('ac_local', 'activity_centre_local'),
        ('ac_complete', 'activity_centre_complete'),
    ]:
        if table in r.tables:
            record(layer, r.get_gdf(f'SELECT geom FROM {table}'))

    for layer, table in [
        ('pos_any', 'aos_public_any_nodes_30m_line'),
        ('pos_large', 'aos_public_large_nodes_30m_line'),
    ]:
        if table in r.tables:
            has_aos = 'aos_public' in r.tables
            sql = f"""SELECT n.geom,
                           {'ROUND(a.aos_ha_public::numeric, 2) AS aos_ha' if has_aos else 'NULL AS aos_ha'}
                    FROM {table} n
                    {"LEFT JOIN aos_public a ON a.aos_id = n.aos_id" if has_aos else ''}"""
            record(layer, r.get_gdf(sql))

    boundary = r.get_gdf(
        'SELECT study_region, area_sqkm, pop_est, geom FROM urban_study_region',
    )
    record('boundary', boundary)

    buffer_table = r.config.get('buffered_urban_study_region')
    if buffer_table and buffer_table in r.tables:
        record('buffer', r.get_gdf(f'SELECT geom FROM {buffer_table}'))
    manifest['bbox'] = [
        round(float(v), 5) for v in boundary.to_crs(4326).total_bounds
    ]
    # population-weighted centre, where the dashboard opens.  The bbox midpoint can
    # sit far from the city when the urban area includes small detached fragments:
    # Minneapolis's 3.6 km2 share of the Saint Cloud urban centre, 75 km away, put
    # its bbox midpoint 35 km from where people live.
    manifest['center'] = population_centre(r)
    # size, population and network composition, for the dashboard's city grouping
    manifest['profile'] = city_profile(r)
    manifest['grid_columns'] = g_cols
    # the region's own measures, for the dashboard's destination menu: only those
    # with results, each giving its strict/lenient indicator names and labels
    exported_overlays = set()
    if 'custom_dest' in manifest['layers']:
        exported_overlays = {
            name
            for ind in custom
            for name, o in ind['overlays'].items()
            if o['layer'] in r.tables
        }
    manifest['custom_indicators'] = [
        {
            'name': ind['name'],
            'kind': ind['kind'],
            'label': ind['label'],
            'description': ind['description'],
            'strict': ind['variants']['strict']['name'],
            'lenient': ind['variants']['lenient']['name'],
            'strict_label': ind['variants']['strict']['label'],
            'lenient_label': ind['variants']['lenient']['label'],
            'overlay': sorted(exported_overlays & set(ind['overlays'])),
            'members': ind.get('members'),
        }
        for ind in custom
        if any(
            f'pct_access_cycle_{fam}{v["name"]}_2000m' in g_cols
            for fam in GRID_FAMILIES
            for v in ind['variants'].values()
        )
    ]

    # population-weighted region-overall value for each grid column (pop_ prefix
    # in indicators_region), for display alongside the selected indicator
    region_cols = [
        c
        for c in g_cols
        if f'pop_{c}' in existing_columns(r, 'indicators_region')
    ]
    if region_cols:
        row = r.get_df(
            'SELECT '
            + ', '.join(
                f'ROUND(pop_{c}::numeric, 1) AS {c}' for c in region_cols
            )
            + ' FROM indicators_region',
        ).iloc[0]
        manifest['region_values'] = {
            c: (None if row[c] is None or row[c] != row[c] else float(row[c]))
            for c in region_cols
        }

    grid_df = r.get_df(
        f'SELECT pop_est, {", ".join(g_cols)} FROM indicators_100m_2025',
    )
    manifest['distributions'] = grid_distributions(
        r,
        g_cols,
        categories,
        df=grid_df,
    )
    manifest['grid_stats'] = grid_stats(grid_df, g_cols)

    with open(f'{outdir}/manifest.json', 'w') as f:
        json.dump(manifest, f, indent=1)
    print(f'  manifest.json written; bbox {manifest["bbox"]}', flush=True)


AVG_BIN_M = 500  # histogram bin width for average-distance distributions
AVG_MAX_M = 5000  # values beyond this clip into the last bin
# dismount-dependence classes: (exclusive lower, inclusive upper) bounds on the
# percentage of a cell's sample points whose access depends on dismounting.  The
# first class is the "none at all" case, so its lower bound is below zero.  The
# breaks are wide because a 100 m cell holds only a handful of sample points, so
# the percentage is coarse (one point in five is already 20%).
GAP_CLASSES = [(-1, 0), (0, 10), (10, 25), (25, 50), (50, 100)]


def _weighted_quantile(values, weights, q):
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cw = np.cumsum(w)
    if cw[-1] <= 0:
        return None
    return float(np.interp(q * cw[-1], cw, v))


# continuous distance columns summarised as box plots in the dashboard's all-cities
# ranking; access percentages are bounded 0-100 and are not summarised this way
BOX_PREFIXES = ('avg_cycle_dist_', f'avg_cycle_extra_{DMGAP_FAMILY}')


def tukey_summary(values):
    """Unweighted Tukey box-plot summary of grid cell values, in integer metres.

    q1/med/q3 use linear interpolation; lo/hi are the most extreme values within
    1.5 x IQR of the box, and n_low/n_high count the cells beyond them.
    Mirrored by validation-site/build/backfill_grid_stats.py -- keep in step.
    """
    v = np.asarray(values, dtype=float)
    v = v[~np.isnan(v)]
    if not len(v):
        return None
    q1, med, q3 = np.percentile(v, [25, 50, 75])
    fence_lo, fence_hi = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    inside = v[(v >= fence_lo) & (v <= fence_hi)]
    return {
        'n': int(len(v)),
        'q1': round(float(q1)),
        'med': round(float(med)),
        'q3': round(float(q3)),
        'lo': round(float(inside.min())),
        'hi': round(float(inside.max())),
        'min': round(float(v.min())),
        'max': round(float(v.max())),
        'n_low': int((v < fence_lo).sum()),
        'n_high': int((v > fence_hi).sum()),
    }


def grid_stats(df, g_cols):
    """Box-plot summaries of each continuous grid column (see tukey_summary)."""
    out = {}
    for col in g_cols:
        if col.startswith(BOX_PREFIXES) and col in df.columns:
            # summarise the values as tiled (the grid layer's ROUND(...)::int, half
            # away from zero), so the ranking describes the cells the map shows
            v = df[col].to_numpy(dtype=float)
            summary = tukey_summary(np.sign(v) * np.floor(np.abs(v) + 0.5))
            if summary:
                out[col] = summary
    return out


def grid_distributions(r, g_cols, categories=GRID_CATEGORIES, df=None):
    """Population-weighted distributions per indicator permutation.

    Feeds the dashboard's summary histogram.

    For each <family><category>:
      'iso' -- % of population in each access band (500/1000/2000/5000 m /
               no access), banding each cell by the smallest distance at which
               >= 50% of its sample points have access (the dashboard/report
               isochrone rule);
      'avg' -- % of (reachable) population per AVG_BIN_M distance-to-nearest
               bin from 0 to AVG_MAX_M (last bin includes beyond), plus
               weighted p25/p50/p75.

    The dmgap_ contrast gets its own 'gap' entry instead: per distance threshold, the
    % of population in each dismount-dependence class (see GAP_CLASSES) — the classes
    the dashboard's dismount-dependence choropleth colours by.
    """
    if df is None:
        df = r.get_df(
            f'SELECT pop_est, {", ".join(g_cols)} FROM indicators_100m_2025',
        )
    pop = df['pop_est'].fillna(0).to_numpy(dtype=float)
    total = pop.sum()
    if total <= 0:
        return {}
    out = {}
    for fam in GRID_FAMILIES:
        for cat in categories:
            entry = {}
            band_cols = [
                f'pct_access_cycle_{fam}{cat}_{d}' for d in GRID_DISTANCES
            ]
            if f'pct_access_cycle_{fam}{cat}_2000m' in df.columns:
                band = np.full(len(df), len(GRID_DISTANCES))
                for i, col in reversed(list(enumerate(band_cols))):
                    if col in df.columns:
                        band[df[col].fillna(-1).to_numpy() >= 50] = i
                entry['iso'] = [
                    round(float(pop[band == i].sum() / total * 100), 1)
                    for i in range(len(GRID_DISTANCES) + 1)
                ]
            acol = f'avg_cycle_dist_{fam}{cat}'
            if acol in df.columns:
                v = df[acol].to_numpy(dtype=float)
                mask = ~np.isnan(v)
                w = pop[mask]
                if w.sum() > 0:
                    vv = np.clip(v[mask], 0, AVG_MAX_M)
                    idx = np.minimum(
                        (vv // AVG_BIN_M).astype(int),
                        AVG_MAX_M // AVG_BIN_M - 1,
                    )
                    shares = [
                        round(float(w[idx == i].sum() / w.sum() * 100), 1)
                        for i in range(AVG_MAX_M // AVG_BIN_M)
                    ]
                    entry['avg'] = {
                        'bin_m': AVG_BIN_M,
                        'max_m': AVG_MAX_M,
                        'shares': shares,
                        'p25': round(
                            _weighted_quantile(v[mask], w, 0.25) or 0,
                        ),
                        'p50': round(
                            _weighted_quantile(v[mask], w, 0.50) or 0,
                        ),
                        'p75': round(
                            _weighted_quantile(v[mask], w, 0.75) or 0,
                        ),
                    }
            if entry:
                out[f'{fam}{cat}'] = entry
    for cat in categories:
        gap = {}
        for dist in GRID_DISTANCES:
            col = f'pct_access_cycle_{DMGAP_FAMILY}{cat}_{dist}'
            if col not in df.columns:
                continue
            v = df[col].fillna(0).to_numpy(dtype=float)
            gap[dist] = [
                round(float(pop[(v > lo) & (v <= hi)].sum() / total * 100), 1)
                for lo, hi in GAP_CLASSES
            ]
        extra = f'avg_cycle_extra_{DMGAP_FAMILY}{cat}'
        if gap:
            entry = {'gap': gap}
            if extra in df.columns:
                v = df[extra].to_numpy(dtype=float)
                # averaged only over cells where riding around the walked links
                # actually costs something: most residents never touch one, so
                # including them would report a near-zero detour everywhere
                mask = ~np.isnan(v) & (v > 0)
                w = pop[mask]
                if w.sum() > 0:
                    entry['extra_mean'] = round(
                        float((w * v[mask]).sum() / w.sum()),
                    )
                    entry['extra_pop_pct'] = round(
                        float(w.sum() / total * 100),
                        1,
                    )
            out[f'{DMGAP_FAMILY}{cat}'] = entry
    return out


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    export(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
