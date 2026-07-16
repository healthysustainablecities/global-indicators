"""Export cycling-validation map layers from a region database to GeoJSONSeq.

Produces the per-layer newline-delimited GeoJSON inputs for building a single
<slug>.pmtiles vector-tile archive per city (via tippecanoe, run separately),
for the round-2 interactive validation site.

Layers exported (EPSG:4326):
    lts          edges with an LTS rating + popup attributes
    grid         100m indicators grid, headline cycling access + distance columns
    destinations point destinations (dest_name / dest_name_full)
    pos_any      public open space entry lines (any)
    pos_large    public open space entry lines (large)
    ac_local     local activity centre clusters
    ac_complete  complete activity centre clusters
    boundary     urban study region

Usage (inside the ghsci container):
    /env/bin/python _export_validation_tiles.py "data/Cycling/Würzburg/Würzburg.yml" [outdir]

Default outdir is /tmp/validation_tiles/<slug>/ (copy out with docker cp).
A manifest.json is written alongside the layer files with bbox, feature counts
and the layer list, for consumption by the tile build script and the site.
"""

import json
import os
import re
import sys
import unicodedata

os.chdir('/home/ghsci/process')
sys.path.insert(0, '/home/ghsci/process/subprocesses')

import ghsci  # noqa: E402

# Grid measure families ('' = danger-weighted, 'safe_' = fully low-stress LTS 1-2
# route, 'lts1_' = LTS 1 only) x destination categories x distance thresholds.
# Only columns that exist in the region database are exported; the viewer reads
# manifest.json grid_columns to know which permutations a city supports.
GRID_FAMILIES = ['', 'safe_', 'lts1_']
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


def slugify(name):
    ascii_name = (
        unicodedata.normalize('NFKD', name)
        .encode('ascii', 'ignore')
        .decode('ascii')
    )
    return re.sub(r'[^a-z0-9]+', '_', ascii_name.lower()).strip('_')


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


def grid_columns(r):
    available = existing_columns(r, 'indicators_100m_2025')
    cols = []
    for fam in GRID_FAMILIES:
        for cat in GRID_CATEGORIES:
            for dist in GRID_DISTANCES:
                cols.append(f'pct_access_cycle_{fam}{cat}_{dist}')
        for cat in GRID_CATEGORIES:
            cols.append(f'avg_cycle_dist_{fam}{cat}')
    return [c for c in cols if c in available]


def export(codename, outdir=None):
    r = ghsci.Region(codename)
    slug = slugify(r.name)
    outdir = outdir or f'/tmp/validation_tiles/{slug}'
    os.makedirs(outdir, exist_ok=True)
    manifest = {'name': r.name, 'codename': codename, 'slug': slug, 'layers': {}}

    def record(layer, gdf):
        n = write_layer(gdf, f'{outdir}/{layer}.geojsonl')
        manifest['layers'][layer] = {'file': f'{layer}.geojsonl', 'features': n}
        print(f'  {layer}: {n} features', flush=True)

    print(f'{r.name} -> {outdir}', flush=True)

    edge_cols = [c for c in EDGE_COLUMNS if c in existing_columns(r, 'edges')]
    lts = r.get_gdf(
        f"""SELECT {', '.join(edge_cols)},
                   ROUND(length::numeric) AS length_m, geom
            FROM edges WHERE lvl_traf_stress IS NOT NULL""",
    ).drop(columns=['length'], errors='ignore')
    record('lts', lts)

    g_cols = grid_columns(r)
    # integer values (pct 0-100, distances in m): halves tile size via value dedup
    rounded = ', '.join(f'ROUND({c}::numeric)::int AS {c}' for c in g_cols)
    record(
        'grid',
        r.get_gdf(f'SELECT {rounded}, geom FROM indicators_100m_2025'),
    )

    record(
        'destinations',
        r.get_gdf(
            f"""SELECT dest_name, dest_name_full, geom FROM destinations
                WHERE dest_name IN {INDICATOR_DEST_NAMES}""",
        ),
    )
    if 'pt_stops_headway' in r.tables:
        record(
            'pt_frequent',
            r.get_gdf(
                """SELECT stop_name, mode, headway, geom
                   FROM pt_stops_headway WHERE headway <= 20""",
            ),
        )
    for layer, table in [
        ('pos_any', 'aos_public_any_nodes_30m_line'),
        ('pos_large', 'aos_public_large_nodes_30m_line'),
        ('ac_local', 'activity_centre_local'),
        ('ac_complete', 'activity_centre_complete'),
    ]:
        if table in r.tables:
            record(layer, r.get_gdf(f'SELECT geom FROM {table}'))

    boundary = r.get_gdf(
        'SELECT study_region, area_sqkm, pop_est, geom FROM urban_study_region',
    )
    record('boundary', boundary)
    manifest['bbox'] = [
        round(float(v), 5) for v in boundary.to_crs(4326).total_bounds
    ]
    manifest['grid_columns'] = g_cols

    # population-weighted region-overall value for each grid column (pop_ prefix
    # in indicators_region), for display alongside the selected indicator
    region_cols = [c for c in g_cols if f'pop_{c}' in existing_columns(r, 'indicators_region')]
    if region_cols:
        row = r.get_df(
            'SELECT '
            + ', '.join(f'ROUND(pop_{c}::numeric, 1) AS {c}' for c in region_cols)
            + ' FROM indicators_region',
        ).iloc[0]
        manifest['region_values'] = {
            c: (None if row[c] is None or row[c] != row[c] else float(row[c]))
            for c in region_cols
        }

    with open(f'{outdir}/manifest.json', 'w') as f:
        json.dump(manifest, f, indent=1)
    print(f'  manifest.json written; bbox {manifest["bbox"]}', flush=True)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    export(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
