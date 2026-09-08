"""Derive the cut-down datasets for the GHSCI Las Palmas example.

Every input is an official, openly licensed source; this script records exactly
how each small example dataset was derived from it, so that the example can be
regenerated, or adapted for another city.

Run inside the GHSCI container, for example:

    python prepare_example_data.py \
        --source /home/ghsci/process/data \
        --out /home/ghsci/process/data/examples/ES_Las_Palmas_2025

Individual steps may be selected with --steps, for example:

    python prepare_example_data.py --steps population gtfs
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

import geopandas as gpd
import rasterio
from rasterio.mask import mask

# REGCAN95 / LAEA Europe, the projected CRS for the Canary Islands, used as
# the study region CRS in the region configuration.
CRS = 5635
# The GHSCI study region buffer (configuration/config.yml study_buffer) plus a
# margin, so that clipped inputs comfortably cover the buffered study region.
BUFFER_M = 2500

# Global Human Settlement Layer population grid.  The 2025 epoch of the R2023A
# release at 100 m in the Mollweide projection; tile R6_C17 covers the Canary
# Islands.  Only the clip is published with the example; the tile is ~90 MB.
POPULATION_TILE = 'GHS_POP_E2025_GLOBE_R2023A_54009_100_V1_0_R6_C17'
POPULATION_URL = (
    'https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/'
    'GHS_POP_GLOBE_R2023A/GHS_POP_E2025_GLOBE_R2023A_54009_100/V1-0/'
    f'tiles/{POPULATION_TILE}.zip'
)

# Global Human Settlement Layer Urban Centre Database.  The R2024A release is
# a single geopackage of sixteen thematic layers; the general characteristics
# layer carries the identifying attributes used to select an urban centre.
UCDB = 'urban_regions/GHS_UCDB_GLOBE_R2024A_V1_0/GHS_UCDB_GLOBE_R2024A.gpkg'
UCDB_LAYER = 'GHS_UCDB_THEME_GENERAL_CHARACTERISTICS_GLOBE_R2024A'
UCDB_WHERE = (
    "GC_UCN_MAI_2025 = 'Las Palmas de Gran Canaria' "
    "AND GC_CNT_GAD_2025 = 'Spain'"
)

# OpenStreetMap.  The Canary Islands extract is clipped to the buffered study
# region boundary, reducing 59 MB to a few MB.
OSM_EXTRACT = 'canary-islands-260728.osm.pbf'
OSM_CLIP = 'las_palmas-260728.osm.pbf'
OSM_URL = (
    'https://download.openstreetmap.fr/extracts/africa/spain/canarias/'
    'las_palmas-latest.osm.pbf'
)

# Guaguas, the municipal bus operator for Las Palmas de Gran Canaria.
GTFS_URL = 'https://www.guaguas.com/transit/google_transit.zip'
# The analysis window configured in the region configuration.  Chosen as
# a two month period of ordinary service: every service in calendar.txt
# runs 2015-2035, and no calendar_dates.txt exception falls within it.
GTFS_WINDOW = ('20250405', '20250605')

# Datasets carried over unchanged from the source-type folders used by the
# superseded 2023 example.  Municipal boundaries are stable, so the boundary
# extracted from the Centro Nacional de Informacion Geografica 'lineas limite'
# release is reused rather than re-cut from that several hundred megabyte
# national download.
COPIES = [
    (
        'region_boundaries/Example/Las Palmas de Gran Canaria - Centro '
        'Nacional de Información Geográfica - WGS84 - EPSG4326.geojson',
        'boundaries/las_palmas_municipality.geojson',
    ),
    (
        'region_boundaries/Example/Las Palmas excerpt- '
        'gobcan_educacion_areainfluenciacentrosecundaria.geojson',
        'boundaries/school_districts.geojson',
    ),
    (
        'policy_review/'
        'gohsc-policy-indicator-checklist-example-ES-Las-Palmas-2023.xlsx',
        'policy/gohsc-policy-indicator-checklist-example-ES-Las-Palmas.xlsx',
    ),
]
IMAGES = [
    'Example image of a vibrant, walkable, urban neighbourhood'
    ' - landscape.jpg',
    'Example image 2-Landscape.jpg',
    'Example image of a vibrant, walkable, urban neighbourhood - square.jpg',
    'Example image of climate resilient lively city watercolor-Square.jpg',
]


def log(message):
    print(message, flush=True)


def download(url, destination):
    """Retrieve a file, reporting its size.

    A browser user agent is sent because some providers, the Guaguas GTFS
    endpoint among them, answer the default Python user agent with 403.
    """
    log(f'  downloading {url}')
    request = urllib.request.Request(
        url,
        headers={
            'User-Agent': (
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/120 Safari/537.36'
            ),
        },
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        data = response.read()
    with open(destination, 'wb') as f:
        f.write(data)
    log(f'  wrote {destination} ({len(data):,} bytes)')


def study_region(source, out):
    """Return the boundary, and its buffer, in the study region CRS."""
    path = f'{out}/boundaries/las_palmas_municipality.geojson'
    if not os.path.isfile(path):
        copy_source_datasets(source, out)
    boundary = gpd.read_file(path).to_crs(CRS)
    return boundary, boundary.buffer(BUFFER_M)


def copy_source_datasets(source, out):
    """Copy the datasets that are reused unchanged."""
    for relative, destination in COPIES:
        target = f'{out}/{destination}'
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(f'{source}/{relative}', target)
        log(f'  {destination} ({os.path.getsize(target):,} bytes)')


def prepare_boundaries(source, out):
    """Copy the municipal boundary and school district catchments."""
    log('Boundaries')
    copy_source_datasets(source, out)


def prepare_images(source, out):
    """Copy the illustrative report images."""
    log('Report images')
    assets = f'{os.path.dirname(source)}/configuration/assets'
    for name in IMAGES:
        target = f'{out}/images/{name}'
        shutil.copyfile(f'{assets}/{name}', target)
        log(f'  images/{name} ({os.path.getsize(target):,} bytes)')


def prepare_population(source, out):
    """Download the GHS-POP tile and clip it to the buffered boundary."""
    log('Population (GHS-POP E2025 R2023A, 100 m Mollweide)')
    boundary, buffered = study_region(source, out)
    target = f'{out}/population/ghsl_100m/{POPULATION_TILE}.tif'
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive = f'{tmp}/{POPULATION_TILE}.zip'
        download(POPULATION_URL, archive)
        with zipfile.ZipFile(archive) as z:
            z.extractall(tmp)
        tif = f'{tmp}/{POPULATION_TILE}.tif'
        with rasterio.open(tif) as raster:
            # the clip is taken in the raster's own Mollweide projection, so
            # that no resampling occurs here; GHSCI reprojects at run time
            shape = buffered.to_crs(raster.crs).union_all()
            data, transform = mask(raster, [shape], crop=True)
            profile = raster.profile
        profile.update(
            height=data.shape[1],
            width=data.shape[2],
            transform=transform,
            compress='deflate',
        )
        with rasterio.open(target, 'w', **profile) as clipped:
            clipped.write(data)
    with rasterio.open(target) as clipped:
        total = clipped.read(1)
        total = float(total[total > 0].sum())
    log(f'  {target} ({os.path.getsize(target):,} bytes)')
    log(f'  clipped population total: {total:,.0f}')


def prepare_urban_region(source, out):
    """Cut the Las Palmas record from the Urban Centre Database."""
    log('Urban region (GHS-UCDB R2024A)')
    target = f'{out}/urban_region/GHS_UCDB_R2024A_Las_Palmas.gpkg'
    centre = gpd.read_file(
        f'{source}/{UCDB}',
        layer=UCDB_LAYER,
        where=UCDB_WHERE,
    )
    if len(centre) != 1:
        sys.exit(
            f'Expected exactly one urban centre, found {len(centre)}.  '
            f'Check the query: {UCDB_WHERE}',
        )
    centre.to_file(target, layer='urban_centre', driver='GPKG')
    log(f'  {target} ({os.path.getsize(target):,} bytes)')
    log(
        f'  {centre.iloc[0]["GC_UCN_MAI_2025"]}, '
        f'{centre.iloc[0]["GC_CNT_GAD_2025"]}: '
        f'{centre.iloc[0]["GC_POP_TOT_2025"]:,.0f} people, '
        f'{centre.iloc[0]["GC_UCA_KM2_2025"]} km2',
    )


def prepare_openstreetmap(source, out):
    """Clip the Canary Islands extract to the buffered boundary."""
    log('OpenStreetMap')
    boundary, buffered = study_region(source, out)
    extract = f'{out}/{OSM_EXTRACT}'
    if not os.path.isfile(extract):
        sys.exit(
            f'The OpenStreetMap extract is expected at {extract}.\n'
            f'Download it from {OSM_URL}',
        )
    poly = f'{out}/openstreetmap/{OSM_CLIP.replace(".osm.pbf", ".poly")}'
    target = f'{out}/openstreetmap/{OSM_CLIP}'
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        # osmconvert clips against a polygon filter file in WGS84, the same
        # tool and .poly format the analysis itself uses (see
        # subprocesses/_02_create_osm_resources.py)
        wgs84 = f'{tmp}/buffered.geojson'
        gpd.GeoDataFrame(geometry=buffered, crs=CRS).to_crs(4326).to_file(
            wgs84,
            driver='GeoJSON',
        )
        subprocess.check_call(
            [
                sys.executable,
                '/home/ghsci/process/subprocesses/ogr2poly.py',
                wgs84,
            ],
            cwd=tmp,
        )
        produced = [x for x in os.listdir(tmp) if x.endswith('.poly')]
        if not produced:
            sys.exit('ogr2poly.py did not produce a .poly file')
        shutil.copyfile(f'{tmp}/{produced[0]}', poly)
    if os.path.isfile(target):
        os.remove(target)
    subprocess.check_call(
        ['osmconvert', extract, f'-B={poly}', f'-o={target}'],
    )
    log(f'  {poly} ({os.path.getsize(poly):,} bytes)')
    log(
        f'  {target} ({os.path.getsize(target):,} bytes, '
        f'from {os.path.getsize(extract):,})',
    )


def prepare_gtfs(source, out):
    """Download the current Guaguas GTFS feed and report its coverage."""
    log('GTFS (Guaguas)')
    target = f'{out}/gtfs/gtfs_es_las_palmas_guaguas.zip'
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        downloaded = f'{tmp}/google_transit.zip'
        download(GTFS_URL, downloaded)
        # the published feed is packed on macOS and carries '__MACOSX'
        # resource fork entries; repack with only the GTFS tables so that
        # what ships with the example is exactly what is analysed
        with zipfile.ZipFile(downloaded) as source_zip:
            wanted = [
                n
                for n in sorted(source_zip.namelist())
                if n.endswith('.txt') and not n.startswith('__MACOSX/')
            ]
            with zipfile.ZipFile(
                target,
                'w',
                zipfile.ZIP_DEFLATED,
            ) as repacked:
                for name in wanted:
                    repacked.writestr(name, source_zip.read(name))
    with zipfile.ZipFile(target) as z:
        log(f'  {target} ({os.path.getsize(target):,} bytes)')
        log(f'  files: {", ".join(sorted(z.namelist()))}')
        summarise_gtfs_calendar(z)
        summarise_gtfs_modes(z)


def summarise_gtfs_calendar(z):
    """Report the service date range, to inform the configured window.

    A configured analysis window that falls outside a mode's service dates
    silently drops that mode from the analysis, so the window has to be
    checked against calendar.txt and calendar_dates.txt rather than assumed.
    """
    import csv
    import io

    dates = []
    if 'calendar.txt' in z.namelist():
        with z.open('calendar.txt') as f:
            for row in csv.DictReader(io.TextIOWrapper(f, 'utf-8-sig')):
                dates += [row['start_date'], row['end_date']]
    if 'calendar_dates.txt' in z.namelist():
        with z.open('calendar_dates.txt') as f:
            rows = list(csv.DictReader(io.TextIOWrapper(f, 'utf-8-sig')))
            dates += [
                r['date'] for r in rows if r.get('exception_type') == '1'
            ]
    if dates:
        log(f'  service dates span {min(dates)} to {max(dates)}')
    else:
        log('  no service dates found; check the feed')


def summarise_gtfs_modes(z):
    """Report the modes present, and the exceptions in the configured window.

    The configured window is stated here so that regenerating the feed
    re-checks it: if a future release of the feed introduces service
    exceptions within the window, or a new mode, that shows up in this
    output rather than as a quietly incomplete analysis.
    """
    import csv
    import io

    ROUTE_TYPES = {
        '0': 'Tram',
        '1': 'Metro',
        '2': 'Rail',
        '3': 'Bus',
        '4': 'Ferry',
    }
    with z.open('routes.txt') as f:
        routes = list(csv.DictReader(io.TextIOWrapper(f, 'utf-8-sig')))
    counts = {}
    for route in routes:
        mode = ROUTE_TYPES.get(route['route_type'], route['route_type'])
        counts[mode] = counts.get(mode, 0) + 1
    log(f'  modes: {counts}')

    start, end = GTFS_WINDOW
    inside = []
    if 'calendar_dates.txt' in z.namelist():
        with z.open('calendar_dates.txt') as f:
            inside = [
                r
                for r in csv.DictReader(io.TextIOWrapper(f, 'utf-8-sig'))
                if start <= r['date'] <= end
            ]
    log(
        f'  configured window {start}-{end}: '
        f'{len(inside)} service exceptions'
        + (
            ''
            if not inside
            else '  <-- review, these alter service in the window'
        ),
    )


STEPS = {
    'boundaries': prepare_boundaries,
    'images': prepare_images,
    'population': prepare_population,
    'urban_region': prepare_urban_region,
    'openstreetmap': prepare_openstreetmap,
    'gtfs': prepare_gtfs,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='/home/ghsci/process/data')
    parser.add_argument(
        '--out',
        default='/home/ghsci/process/data/examples/ES_Las_Palmas_2025',
    )
    parser.add_argument(
        '--steps',
        nargs='+',
        choices=sorted(STEPS),
        default=None,
    )
    args = parser.parse_args()
    for name in args.steps or list(STEPS):
        STEPS[name](args.source, args.out)


if __name__ == '__main__':
    main()
