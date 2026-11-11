"""
Generate Google Earth Engine indicators.

1. Large Public Urban Green Space (LPUGS)
2. Global Urban Heat Vulnerability Index (GUHVI)
"""

import json
import os
import re
import shutil
import tempfile
import time
import warnings

import ee
import geemap
import geopandas as gpd
import ghsci
import numpy as np
import psycopg2
import rasterio
import rasterio.mask
import requests
from rasterio.io import MemoryFile
from shapely import wkt
from shapely.ops import unary_union
from sqlalchemy import create_engine, text

warnings.filterwarnings('ignore', message="Couldn't find STAC entry for")
warnings.filterwarnings(
    'ignore',
    message="'BaseImage' is deprecated and will be removed",
)


def clean_city_name_for_gee(city_name):
    """
    Clean city name to meet Google Earth Engine asset naming requirements.

    Requirements:
    - Each segment must contain only: a..z, A..Z, 0..9, "_" or "-"
    - Each segment must be at least 1 character long and at most 100 characters long

    Args:
        city_name (str): Original city name

    Returns
    -------
        str: Cleaned city name suitable for GEE asset paths
    """
    # Replace spaces and common separators with underscores
    cleaned = city_name.replace(' ', '_')

    # Remove or replace invalid characters (keep only alphanumeric, underscore, hyphen)
    # This will remove commas, periods, apostrophes, etc.
    cleaned = re.sub(r'[^a-zA-Z0-9_-]', '', cleaned)

    # Remove consecutive underscores or hyphens
    cleaned = re.sub(r'[_-]+', '_', cleaned)

    # Remove leading/trailing underscores or hyphens
    cleaned = cleaned.strip('_-')

    # Ensure length is within limits (max 100 characters)
    if len(cleaned) > 100:
        cleaned = cleaned[:100].rstrip('_-')

    # Ensure at least 1 character
    if not cleaned:
        cleaned = 'city'

    return cleaned


def initialize_gee():
    """Initialize Google Earth Engine using the quota_project_id from the Google Cloud credentials file."""
    # Path to Google Cloud credentials
    adc_path = os.path.expanduser(
        '~/.config/gcloud/application_default_credentials.json',
    )

    try:
        # Read the project_id from credentials file and define project_id as a global variable
        with open(adc_path) as f:
            credentials = json.load(f)
            global project_id
            project_id = credentials.get('quota_project_id')

            if project_id:
                print(
                    f"\nInitializing Earth Engine with project: {project_id}",
                )
                ee.Initialize(project=project_id)
                # Generous client deadline: Earth Engine on-demand compute can
                # take several minutes for large regions (e.g. the GUHVI
                # composite and raster downloads); without this the client would
                # abort requests that would otherwise complete.
                ee.data.setDeadline(600000)
            else:
                print(
                    '\nNo Earth Engine project id found in saved credentials file.',
                )
        return project_id

    except Exception as e:
        print(f"Error initializing Earth Engine: {str(e)}")
        raise


# Function to mask clouds in Sentinel-2 imagery
def mask_s2_clouds(image):
    qa = image.select('QA60')
    cloud_mask = 1 << 10
    cirrus_mask = 1 << 11
    mask = (
        qa.bitwiseAnd(cloud_mask).eq(0).And(qa.bitwiseAnd(cirrus_mask).eq(0))
    )
    return (
        image.updateMask(mask)
        .divide(10000)
        .select(['B.*'])
        .copyProperties(image, ['system:time_start'])
    )


# Function to calculate NDVI
def calculate_ndvi(image):
    ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
    return image.addBands(ndvi)


def validate_lpugs_raster(path):
    """
    Check that a downloaded LPUGS NDVI raster is readable and contains valid data.

    A raster left behind by an interrupted download may be truncated or contain
    only nodata (-9999) values; such a file would otherwise be silently reused,
    resulting in spuriously empty LPUGS indicator results.

    Returns
    -------
        bool: True if the raster opens and contains at least one valid NDVI
        pixel (finite, within [-1, 1]), False otherwise.
    """
    if not os.path.exists(path):
        return False
    try:
        with rasterio.open(path) as src:
            if src.width == 0 or src.height == 0:
                return False
            band = src.read(1)
            valid = np.isfinite(band) & (band >= -1.0) & (band <= 1.0)
            return bool(valid.any())
    except Exception:
        return False


# Earth Engine caps a single getDownloadURL request at ~48 MiB of uncompressed
# pixel data; regions whose output would exceed this must use the tiled path.
GEE_DIRECT_DOWNLOAD_LIMIT_BYTES = 50331648

def download_gee_geotiff(image, out_tif, region, scale, crs, est_bytes, label='LPUGS'):
    """
    Download an Earth Engine image (one or more bands) to a local GeoTIFF.

    Regions small enough to fit within the Earth Engine single-request limit are
    fetched in one ``getDownloadURL`` call, writing raw bytes straight to disk
    (bypassing GDAL/rasterio during download). Larger regions, or any region for
    which the direct request fails, fall back to the geemap/geedim tiled download
    which mosaics multiple tiles to bypass that limit.

    The path is chosen from an up-front size estimate so that an oversized region
    does not fire a direct request that Earth Engine is bound to reject (the
    historical source of the alarming "400 Bad Request" log noise).

    ``label`` is used only to describe the download in the progress output.
    """
    rel_path = out_tif.replace('/home/ghsci/', '')

    if est_bytes < 0.9 * GEE_DIRECT_DOWNLOAD_LIMIT_BYTES:
        try:
            print(
                f"Downloading {label} raster GeoTIFF directly from Google Earth Engine to {rel_path}...",
            )
            url = image.getDownloadURL(
                {
                    'region': region,
                    'scale': scale,
                    'crs': crs,
                    'format': 'GEO_TIFF',
                },
            )
            # Retry transient network/server errors; a definitive size rejection
            # (400/413) or persistent failure drops through to the tiled path.
            last_error = None
            for attempt in range(1, 4):
                try:
                    response = requests.get(url, timeout=600)
                    response.raise_for_status()
                    with open(out_tif, 'wb') as f:
                        f.write(response.content)
                    return
                except requests.RequestException as e:
                    last_error = e
                    status = getattr(e.response, 'status_code', None)
                    if status in (400, 413):
                        break
                    if attempt < 3:
                        wait = 5 * attempt
                        print(
                            f"  Direct download attempt {attempt} failed ({str(e)}); retrying in {wait}s...",
                        )
                        time.sleep(wait)
            raise last_error
        except Exception as e:
            print(
                f"Direct download unavailable for this region ({str(e)}); using tiled download via geemap...",
            )
    else:
        print(
            f"Region too large (~{est_bytes / 1048576:.0f} MiB) for a single Earth Engine request; using tiled download via geemap to {rel_path}...",
        )

    # geedim 2.0 tiled download: mosaics tiles to bypass the single-request size
    # limit. num_threads is intentionally not passed (deprecated and ignored in
    # geedim 2.0); the library's default concurrency is used.
    try:
        geemap.download_ee_image(
            image=image,
            filename=out_tif,
            region=region,
            scale=scale,
            crs=crs,
            dtype='float32',
            unmask_value=-9999,
            overwrite=True,
        )
    except Exception as e:
        raise Exception(
            f"Failed to download {label} GeoTIFF via Earth Engine tiled (geemap) download: {str(e)}",
        )


def rasterise_band_labels(geometries, transform, shape):
    """
    Rasterise cell geometries to 1-based integer labels.

    Returns an ``int32`` array of ``shape`` where every pixel carries the
    1-based index of the cell it falls within (0 = no cell).  The labels are
    used to aggregate a raster into per-cell statistics with ``np.bincount``.
    """
    from rasterio.features import rasterize

    shapes = [
        (geometry, index)
        for index, geometry in enumerate(geometries, start=1)
        if geometry is not None and not geometry.is_empty
    ]
    if not shapes:
        return np.zeros(shape, dtype='int32')
    return rasterize(
        shapes,
        out_shape=shape,
        transform=transform,
        fill=0,
        dtype='int32',
    )


def rasterise_binary(geometries, transform, shape):
    """Rasterise a sequence of geometries to a 1/0 mask of ``shape``."""
    from rasterio.features import rasterize

    shapes = [
        (geometry, 1)
        for geometry in geometries
        if geometry is not None and not geometry.is_empty
    ]
    if not shapes:
        return np.zeros(shape, dtype='uint8')
    return rasterize(
        shapes,
        out_shape=shape,
        transform=transform,
        fill=0,
        dtype='uint8',
    )


def zonal_means_by_band(
    raster_path,
    band_names,
    labels,
    nodata,
    n_cells,
    valid_floor=None,
):
    """
    Compute the mean of each raster band per labelled cell.

    ``labels`` is the integer array produced by ``rasterise_band_labels``
    (0 = outside any cell, 1..n_cells = cell index).  Pixels equal to
    ``nodata`` (or non-finite) are excluded.  Returns a dict mapping each
    band name to a float array of length ``n_cells``, with NaN for cells
    that contain no valid pixel for that band.

    ``valid_floor`` optionally excludes values below a plausibility floor.
    Resampling a sentinel-unmasked image can partially mix the sentinel with
    valid values at layer boundaries, leaving values far below any legitimate
    band value; the floor removes those without touching real data.
    """
    with rasterio.open(raster_path) as src:
        data = src.read().astype('float64')

    flat_labels = labels.ravel().astype('int64')

    means = {}
    for index, name in enumerate(band_names):
        values = data[index].ravel()
        valid = np.isfinite(values)
        if nodata is not None:
            valid &= values != nodata
        if valid_floor is not None:
            valid &= values >= valid_floor
        cell_labels = flat_labels[valid]
        cell_values = values[valid]
        counts = np.bincount(cell_labels, minlength=n_cells + 1)
        sums = np.bincount(
            cell_labels,
            weights=cell_values,
            minlength=n_cells + 1,
        )
        band_means = np.full(n_cells + 1, np.nan)
        has_pixels = counts > 0
        band_means[has_pixels] = sums[has_pixels] / counts[has_pixels]
        means[name] = band_means[1:]
    return means


def overlap_percentage_by_cell(water_mask, labels, n_cells):
    """
    Percentage of each labelled cell not covered by water.

    Mirrors the previous server-side calculation (``100 - water_fraction *
    100``); cells containing no water - or no pixels at all - return 100.
    """
    flat_labels = labels.ravel().astype('int64')
    water = water_mask.ravel().astype('float64')

    counts = np.bincount(flat_labels, minlength=n_cells + 1)
    water_counts = np.bincount(
        flat_labels,
        weights=water,
        minlength=n_cells + 1,
    )
    fraction = np.zeros(n_cells + 1)
    has_pixels = counts > 0
    fraction[has_pixels] = water_counts[has_pixels] / counts[has_pixels]
    return 100.0 * (1.0 - fraction[1:])


def get_study_region_gdfs(r):
    """
    Return the urban study region and its buffered extent as GeoDataFrames.

    The buffered study region table name is derived from the configured
    study buffer distance (e.g. 'urban_study_region_1600m' given the
    default 1600 m buffer), so it is looked up from the region
    configuration rather than assumed.
    """
    buffered = r.config['buffered_urban_study_region']
    gdfs = []
    for table in ['urban_study_region', buffered]:
        gdf = r.get_gdf(table)
        if gdf is None or len(gdf) == 0:
            raise Exception(
                f"Could not retrieve the '{table}' table from the "
                f"'{r.config['db']}' database; this is required for Earth "
                'Engine analysis.  Please check that the study region set up '
                'completed successfully.',
            )
        gdfs.append(gdf)
    return gdfs[0], gdfs[1]


def get_study_region_ee_feature_collections(
    urban_study_region_gdf,
    urban_study_region_1600m_gdf,
    simplify_tolerance=100,
):
    """
    Convert study region GeoDataFrames to Earth Engine feature collections.

    Study region boundaries (e.g. a metropolitan region with a complex
    coastline) can contain hundreds of thousands of vertices.
    ``geemap.gdf_to_ee()`` embeds those coordinates in full in the
    Earth Engine request graph, so any request referencing the geometry --
    notably the ``getDownloadURL``/geedim download region and the GUHVI grid
    and clip operations -- exceeds Earth Engine's ~10 MiB request payload cap
    and fails with "Request payload size exceeds the limit: 10485760 bytes.".
    Simplifying the geometries locally (shapely) before conversion shrinks the
    serialized geometry significantly; a 100 m simplification has no practical
    effect at the 50 m LPUGS raster resolution or the 1 km GUHVI grid.
    A server-side ``.simplify(maxError=100)`` does not
    help here, as the full vertex set is transmitted regardless.

    The original GeoDataFrames are left untouched (copies are simplified) so
    the exact boundary remains available for post-download masking.

    Args:
        urban_study_region_gdf (gpd.GeoDataFrame): Study region geometry.
        urban_study_region_1600m_gdf (gpd.GeoDataFrame): Buffered study region
            geometry.
        simplify_tolerance (float, optional): Simplification tolerance in the
            GeoDataFrame's units (metres for the metric local CRS used for
            study regions).  Defaults to 100 m.

    Returns
    -------
        tuple of ee.FeatureCollection, ee.FeatureCollection: The study region
        and buffered study region feature collections built from the locally
        simplified geometries.
    """

    def _simplify(gdf):
        simplified = gdf.copy()
        # Replace the values of the *existing* active geometry column (e.g.
        # 'geom') rather than adding a new 'geometry' column: having two
        # geometry columns makes geopandas/geemap's GeoJSON round-trip (used
        # by gdf_to_ee) fail with "contains multiple geometry columns".
        geom_col = simplified.geometry.name
        simplified[geom_col] = gdf.geometry.simplify(
            simplify_tolerance,
            preserve_topology=True,
        )
        return simplified

    urban_study_region_fc = geemap.gdf_to_ee(
        _simplify(urban_study_region_gdf),
        geodesic=False,
    )
    urban_study_region_1600m_fc = geemap.gdf_to_ee(
        _simplify(urban_study_region_1600m_gdf),
        geodesic=False,
    )
    return urban_study_region_fc, urban_study_region_1600m_fc


def lpugs_analysis(r):
    """
    Generate Large Public Urban Green Space (LPUGS) indicators.

    1. Identify LPUGS overall greenery and store raster in PostgreSQL database
    2. Identify LPUGS availability as a subset of areas of open space and store in PostgreSQL database
    3. Perform network analysis to determine LPUGS accessibility within 500m
    4. Overlap population grid with accessible network service area to determine service area and store in PostgreSQL database
    """
    print(
        '\nGenerating Large Public Urban Green Space (LPUGS) availability and accessibility indicators',
    )

    # LPUGS OVERALL GREENERY

    # Fetch urban study region data
    (
        urban_study_region_gdf,
        urban_study_region_1600m_gdf,
    ) = get_study_region_gdfs(r)

    # Build compact Earth Engine feature collections: a study region boundary
    # can contain hundreds of thousands of vertices, which pushes any Earth
    # Engine request that references it past the ~10 MiB payload cap ("Request
    # payload size exceeds the limit: 10485760 bytes").  Simplifying locally
    # before conversion keeps request payloads small (no impact at the 50 m
    # LPUGS resolution or 1 km GUHVI grid); the original GeoDataFrames remain
    # available for exact post-download masking.
    (
        urban_study_region_fc,
        urban_study_region_1600m_fc,
    ) = get_study_region_ee_feature_collections(
        urban_study_region_gdf,
        urban_study_region_1600m_gdf,
    )

    # Convert to geometry objects
    geometry = urban_study_region_fc.geometry(1)
    geometry_1600m = urban_study_region_1600m_fc.geometry(1)

    # Simplify geometries to reduce vertex count
    geometry = geometry.simplify(maxError=100)
    geometry_1600m = geometry_1600m.simplify(maxError=100)
    bounding_box_1600m = geometry_1600m.bounds()

    # Fetch the target year and define date range
    target_year = r.config['year']
    start_date = f"{target_year}-01-01"
    end_date = f"{target_year + 1}-01-01"

    # Get the bounding box of urban study region 1600m for Sentinel NDVI data
    bounding_box_1600m = urban_study_region_1600m_fc.geometry().bounds()

    # Fetch local coordinate reference system (CRS) from config file
    crs_metric = r.config['crs_srid']
    srid_int = int(crs_metric.split(':')[1])
    # Fetch city name and clean it
    city = r.config['name']
    clean_city = clean_city_name_for_gee(city)

    out_dir = os.path.join(r.config['region_dir'], 'lpugs_tiles')
    os.makedirs(out_dir, exist_ok=True)
    out_tif = os.path.join(
        out_dir,
        f'GHSCI_LPUGS_Raster_{clean_city}_download.tif',
    )

    if os.path.exists(out_tif) and not validate_lpugs_raster(out_tif):
        print(
            f"\nPreviously downloaded LPUGS raster {out_tif.replace('/home/ghsci/', '')} is corrupt or contains no valid NDVI data (possibly left by an interrupted download); deleting and re-downloading...",
        )
        os.remove(out_tif)

    if not os.path.exists(out_tif):
        print(
            '\nProcessing Sentinel-2 imagery in Google Earth Engine to calculate NDVI and identify overall greenery for LPUGS availability indicator...',
        )
        # Load Sentinel-2 imagery, mask clouds, and calculate NDVI
        sentinel_collection = (
            ee.ImageCollection(
                'COPERNICUS/S2_SR_HARMONIZED',
            )  # Sentinel-2 Surface Reflectance https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED
            .filterBounds(bounding_box_1600m)
            .filterDate(start_date, end_date)
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 90))
            .map(mask_s2_clouds)
            .map(calculate_ndvi)
        )

        # Calculate annual average NDVI and clip to urban study region
        mean_ndvi = (
            sentinel_collection.select('NDVI')
            .mean()
            .clip(urban_study_region_1600m_fc)
            .rename('NDVI')  # Ensure attribute name is maintained
        )

        # Set no data to -9999, clip to urban study region, and cast to float
        filtered_ndvi = (
            mean_ndvi.select('NDVI')
            .clip(urban_study_region_1600m_fc)
            .unmask(-9999)
            .toFloat()
        )

        # Estimate the uncompressed output size (single-band float32) from the
        # study region bounding box to choose the download path up front, rather
        # than firing a direct request Earth Engine would reject for size.
        minx, miny, maxx, maxy = urban_study_region_gdf.total_bounds
        est_bytes = ((maxx - minx) / 50) * ((maxy - miny) / 50) * 4
        download_gee_geotiff(
            image=filtered_ndvi,
            out_tif=out_tif,
            region=geometry,
            scale=50,
            crs=crs_metric,
            est_bytes=est_bytes,
        )
        if not validate_lpugs_raster(out_tif):
            # Fail loudly now, rather than allowing an empty raster to propagate
            # silently through to empty LPUGS indicator results at report time.
            raise Exception(
                f"Downloaded LPUGS raster {out_tif.replace('/home/ghsci/', '')} contains no valid NDVI data; this may reflect a transient Earth Engine issue.  Re-running the analysis will re-download it.",
            )
    try:  # Check if the file was downloaded successfully
        if not os.path.exists(out_tif):
            raise FileNotFoundError(
                f"Expected output file not found: {out_tif.replace('/home/ghsci/', '')}",
            )
        # Read the stitched local file into memory bytes to keep compatibility with existing rasterio workflow
        print(
            f"\nReading downloaded LPUGS GeoTIFF file into memory ({out_tif.replace('/home/ghsci/', '')})...",
        )
        with open(out_tif, 'rb') as f:
            raster_bytes = f.read()
    except Exception as e:
        raise Exception(f"Error reading downloaded GeoTIFF file: {str(e)}")

    # Get WKT representation of the urban study region
    urban_study_region_wkt = urban_study_region_gdf.geometry.iloc[0].wkt

    # Load the downloaded raster into memory
    with MemoryFile(raster_bytes) as memfile:
        with memfile.open() as src:
            # Prepare the mask geometry
            mask_geom = wkt.loads(urban_study_region_wkt)

            # Convert to GeoJSON format for rasterio
            geoms = [mask_geom.__geo_interface__]

            # Get the mask and window
            mask_shape, mask_transform, mask_window = (
                rasterio.mask.raster_geometry_mask(
                    src,
                    geoms,
                    invert=True,  # Invert so area inside geometry is kept
                    crop=True,  # Crop to the extent of the geometry
                )
            )

            if mask_window is None:
                raise ValueError('Geometry does not intersect with raster')

            # Read the data using the window and convert to float32
            data = src.read(window=mask_window).astype(np.float32)

            # Apply the mask to nullify outside pixels with no data and create output array
            fallback_nodata = -9999.0
            out_image = np.full_like(data, fallback_nodata, dtype=np.float32)

            # Only copy pixels within the mask
            for band in range(out_image.shape[0]):
                # Ensure any internal image NoData are also mapped to -9999.0
                band_data = data[band]
                if src.nodata is not None:
                    np.putmask(
                        band_data,
                        band_data == src.nodata,
                        fallback_nodata,
                    )
                out_image[band][mask_shape] = band_data[mask_shape]

            # Get the transform for the clipped area
            out_transform = src.window_transform(mask_window)

            # Update metadata
            out_meta = src.meta.copy()
            out_meta.update(
                {
                    'driver': 'GTiff',
                    'height': mask_window.height,
                    'width': mask_window.width,
                    'transform': out_transform,
                    'nodata': fallback_nodata,
                    'dtype': 'float32',
                },
            )

            # Write the clipped raster to a new memory file
            with MemoryFile() as clipped_memfile:
                with clipped_memfile.open(**out_meta) as dst:
                    dst.write(out_image)

                # Get the bytes of the clipped raster
                clipped_raster_bytes = clipped_memfile.read()

    # Upload raster to PostgreSQL database
    class PostgresRasterStorage:
        def __init__(self, db_config):
            self.db_config = db_config
            self.engine = self._create_engine()

        def _create_engine(self):
            """Create SQLAlchemy engine with connection pooling."""
            return create_engine(
                f'postgresql://{self.db_config["user"]}:{self.db_config["password"]}'
                f'@{self.db_config["host"]}/{self.db_config["database"]}',
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                json_serializer=lambda obj: json.dumps(
                    obj,
                    ensure_ascii=False,
                ),
            )

        def raster_to_db(self, table_name, raster_data):
            """Store raster data in PostgreSQL."""
            import json

            metadata = {
                'source': 'Google Earth Engine',
                'resolution': '50m',
                'crs': crs_metric,
                'ndvi_threshold': 0.2,
            }

            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        f"""
                    DROP TABLE IF EXISTS {table_name};
                    CREATE TABLE {table_name} (
                        id SERIAL PRIMARY KEY,
                        rast raster,
                        acquisition_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        metadata JSONB
                    )
                """,
                    ),
                )

                conn.execute(
                    text(
                        f"""
                    INSERT INTO {table_name} (rast, metadata)
                    VALUES (
                        ST_SetBandNoDataValue(
                            ST_FromGDALRaster(:raster_data),
                            1,  -- Band 1 (NDVI)
                            -9999  -- Explicit nodata value
                        ),
                        (:metadata)::jsonb
                    )
                """,
                    ),
                    {
                        'raster_data': clipped_raster_bytes,
                        'metadata': json.dumps(metadata),
                    },
                )

    db_config = {
        'host': r.config['db_host'],
        'database': r.config['db'],
        'user': r.config['db_user'],
        'password': r.config['db_pwd'],
    }

    dbRasterStorage = PostgresRasterStorage(db_config)
    dbRasterStorage.raster_to_db(
        table_name='lpugs_overall_greenery',
        raster_data=clipped_raster_bytes,
    )

    print("Created 'lpugs_overall_greenery' database table (NDVI>=0.2)")

    # LPUGS AVAILABILITY (PostGIS-based using lpugs_overall_greenery raster)

    with r.engine.begin() as connection:
        # Ensure areas of open space table exists with required columns
        # (aos_public: aos_id, aos_ha_public, geom_public)
        # Only keep polygons >= 1 ha here as in the previous logic

        # Drop and create LPUGS table
        connection.execute(
            text(
                f"""
            DROP TABLE IF EXISTS large_public_urban_green_space;
            CREATE TABLE large_public_urban_green_space (
                lpugs_id SERIAL PRIMARY KEY,
                aos_id INTEGER,
                aos_ha_public FLOAT,
                NDVI_mean FLOAT,
                geom GEOMETRY(MultiPolygon, {srid_int})
            );
        """,
            ),
        )

        # Compute LPUGS stats in PostGIS:
        # - Use lpugs_overall_greenery.rast (NDVI) and aos_public.geom_public
        # - Filter polygons with aos_ha_public >= 1 and polygon geometry
        #
        # NDVI_mean: mean NDVI within polygon, ignoring nodata (-9999)

        sql = f"""
            INSERT INTO large_public_urban_green_space (aos_id, aos_ha_public, NDVI_mean, geom)
            SELECT
                a.aos_id,
                a.aos_ha_public,
                -- Mean NDVI within polygon
                AVG(vals.val) AS ndvi_mean,
                a.geom_public::geometry(MultiPolygon, {srid_int}) AS geom
            FROM
                aos_public a
            CROSS JOIN
                lpugs_overall_greenery r
            CROSS JOIN LATERAL
                ST_Clip(r.rast, a.geom_public) AS clipped_rast
            CROSS JOIN LATERAL
                ST_PixelAsPoints(clipped_rast) AS vals
            WHERE
                -- Include areas of open space of any size: the previous
                -- minimum size threshold (a.aos_ha_public >= 1, i.e. 1 ha)
                -- is no longer applied.  A space still needs valid NDVI data
                -- with a mean >= 0.2 to be included (see HAVING below).
                -- a.aos_ha_public >= 1
                GeometryType(a.geom_public) IN ('POLYGON', 'MULTIPOLYGON')
                -- Ensure only valid NDVI bounds (-1 to 1) are considered to filter out NoData
                AND vals.val >= -1.0
                AND vals.val <= 1.0
            GROUP BY
                a.aos_id,
                a.aos_ha_public,
                a.geom_public
            -- Only retain instances where ndvi_mean is greater than or equal to 0.2
            HAVING AVG(vals.val) >= 0.2;
        """

        connection.execute(text(sql))

        lpugs_count = connection.execute(
            text('SELECT COUNT(*) FROM large_public_urban_green_space'),
        ).scalar()
        if lpugs_count == 0:
            print(
                'Warning: no large public urban green space polygons were identified (no public open space areas >= 1 ha with mean NDVI >= 0.2).  LPUGS accessibility results will be empty; if green space is known to exist in this study region, this may indicate an issue with the NDVI raster retrieved from Earth Engine.',
            )
        else:
            print(
                f'Identified {lpugs_count} large public urban green space polygons (public open space >= 1 ha with mean NDVI >= 0.2)',
            )

        # Whilst we are here, create the lpugs_nodes_30m_line table for LPUGS accessibility network analysis
        connection.execute(
            text(
                """
            DROP TABLE IF EXISTS lpugs_nodes_30m_line;
            CREATE TABLE lpugs_nodes_30m_line AS
            SELECT DISTINCT n.*, l.lpugs_id
            FROM aos_public_any_nodes_30m_line n
            JOIN large_public_urban_green_space l ON n.aos_id = l.aos_id;

            CREATE INDEX lpugs_nodes_30m_line_gix ON lpugs_nodes_30m_line USING GIST (geom);
        """,
            ),
        )

    # Associate nearest network nodes (n1, n2, n1_distance, n2_distance) now,
    # rather than relying on the destination table loop in
    # _11_neighbourhood_analysis.py, which uses a cached table list that
    # pre-dates this table's creation on a first analysis pass (without these
    # columns, LPUGS accessibility silently returns empty results).
    r.add_nearest_node_associations('lpugs_nodes_30m_line')

    print(
        "Created 'large_public_urban_green_space' database table with LPUGS availability polygons (NDVI>=0.2) and 'lpugs_nodes_30m_line' table for accessibility network analysis",
    )


def lpugs_indicators(r, accessible_nodes):
    # CALCULATE LPUGS GIVEN ACCESSIBILITY
    crs_metric = r.config['crs_srid']
    srid_int = int(crs_metric.split(':')[1])
    # Fetch network data
    nodes = r.get_gdf('nodes', index_col='osmid')
    nodes.columns = ['geometry' if x == 'geom' else x for x in nodes.columns]
    nodes = nodes.set_geometry('geometry')
    edges = r.get_gdf('edges')
    edges.columns = ['geometry' if x == 'geom' else x for x in edges.columns]
    edges = edges.set_geometry('geometry')

    # Filter nodes and edges using the accessible_nodes list
    filtered_nodes = nodes.loc[nodes.index.isin(accessible_nodes)].copy()
    filtered_edges = edges[
        (edges['u'].isin(accessible_nodes))
        & (edges['v'].isin(accessible_nodes))
    ].copy()

    # Load population grid
    population_grid_gdf = r.get_gdf(
        f"SELECT grid_id, pop_est, geom FROM {r.config['population_grid']}",
    ).to_crs(crs_metric)

    # Rename population grid's 'geom' to 'geometry' for the spatial join
    population_grid_for_join = population_grid_gdf.rename_geometry('geometry')
    if any(population_grid_for_join.geometry.type == 'MultiPolygon'):
        population_grid_for_join = population_grid_for_join.explode(
            ignore_index=True,
        )
        print(
            'Exploded MultiPolygon geometries in population grid for Earth Engine processing (requires polygon geometries).',
        )
        multipolygon_population_estimate = population_grid_gdf['pop_est'].sum()
        polygon_population_estimate = population_grid_for_join['pop_est'].sum()
        if multipolygon_population_estimate != polygon_population_estimate:
            print(
                f"Warning: Population estimate changed after exploding MultiPolygons. Original: {multipolygon_population_estimate}, After: {polygon_population_estimate}",
            )

    # Create accessibility grid (grid cells intersecting accessible edges)
    lpugs_accessibility_grid = gpd.sjoin(
        population_grid_for_join[['grid_id', 'pop_est', 'geometry']],
        filtered_edges[['geometry']],
        how='inner',
        predicate='intersects',
    )

    # Drop duplicates that may result from the gpd.sjoin() operation above since a single grid cell (grid_id) can intersect with multiple edges in 'filtered_edges'.
    # Each intersection creates a new row in the output, even if the same grid cell is matched multiple times, so we need to filter out duplicates.
    # Also filter to only retain grid cells with a population estimate greater than 0
    lpugs_accessibility_grid = (
        lpugs_accessibility_grid[['grid_id', 'pop_est', 'geometry']]
        .query('pop_est != 0')
        .drop_duplicates('grid_id')
    )

    # Store results in database
    with r.engine.begin() as connection:
        # Drop and create tables
        connection.execute(
            text('DROP TABLE IF EXISTS lpugs_accessible_nodes;'),
        )
        connection.execute(
            text('DROP TABLE IF EXISTS lpugs_accessible_network;'),
        )
        connection.execute(
            text('DROP TABLE IF EXISTS lpugs_accessibility_grid;'),
        )

        # Create and populate accessible nodes table
        connection.execute(
            text(
                f"""
            CREATE TABLE lpugs_accessible_nodes (
                osmid INT8 PRIMARY KEY,
                x FLOAT,
                y FLOAT,
                geom GEOMETRY(Point, {srid_int})
            );
        """,
            ),
        )

        if not filtered_nodes.empty:
            filtered_nodes = filtered_nodes.to_crs(srid_int)
            # Add x,y coordinates if not already present
            if 'x' not in filtered_nodes.columns:
                filtered_nodes['x'] = filtered_nodes.geometry.x
            if 'y' not in filtered_nodes.columns:
                filtered_nodes['y'] = filtered_nodes.geometry.y

            stmt = text(
                f"""
                INSERT INTO lpugs_accessible_nodes (osmid, x, y, geom)
                VALUES (:osmid, :x, :y, ST_SetSRID(ST_GeomFromText(:geom), {srid_int}));
            """,
            )
            params = [
                {
                    'osmid': idx,
                    'x': row['x'],
                    'y': row['y'],
                    'geom': row['geometry'].wkt,
                }
                for idx, row in filtered_nodes.iterrows()
            ]
            connection.execute(stmt, params)

        # Create and populate accessible network table
        connection.execute(
            text(
                f"""
            CREATE TABLE lpugs_accessible_network (
                id SERIAL PRIMARY KEY,
                u INT8,
                v INT8,
                key INT8,
                length FLOAT,
                osmid TEXT,
                geom GEOMETRY(LineString, {srid_int})
            );
        """,
            ),
        )

        if not filtered_edges.empty:
            filtered_edges = filtered_edges.to_crs(srid_int)
            stmt = text(
                f"""
                INSERT INTO lpugs_accessible_network (u, v, key, length, osmid, geom)
                VALUES (:u, :v, :key, :length, :osmid, ST_SetSRID(ST_GeomFromText(:geom), {srid_int}));
            """,
            )
            params = [
                {
                    'u': row['u'],
                    'v': row['v'],
                    'key': row['key'],
                    'length': row['length'],
                    'osmid': str(row['osmid']),
                    'geom': row['geometry'].wkt,
                }
                for _, row in filtered_edges.iterrows()
            ]
            connection.execute(stmt, params)

        # Create and populate accessibility grid table
        connection.execute(
            text(
                f"""
            CREATE TABLE lpugs_accessibility_grid (
                grid_id TEXT PRIMARY KEY,
                pop_est FLOAT,
                geom GEOMETRY(Polygon, {srid_int})
            );
        """,
            ),
        )

        if not lpugs_accessibility_grid.empty:
            stmt = text(
                f"""
                INSERT INTO lpugs_accessibility_grid (grid_id, pop_est, geom)
                VALUES (:grid_id, :pop_est, ST_SetSRID(ST_GeomFromText(:geom), {srid_int}));
            """,
            )
            params = [
                {
                    'grid_id': row['grid_id'],
                    'pop_est': row['pop_est'],
                    'geom': row['geometry'].wkt,
                }
                for _, row in lpugs_accessibility_grid.iterrows()
            ]
            connection.execute(stmt, params)

    print(
        '\nLarge Public Urban Green Space (LPUGS) availability and accessibility indicators complete',
    )


def guhvi_analysis(r):  # noqa: C901
    """
    Generate Global Urban Heat Vulnerability Index (GUHVI) indicators.

    The raw component bands (LST, LSA, NDVI, NDBI, LCZ, population density,
    vulnerable population, child dependency ratio, SHDI and IMR) are built in
    Earth Engine and downloaded as a single multi-band GeoTIFF; the per-cell
    statistics, coastline overlap, normalisation, composites and quintiles are
    then computed locally.

    1. Generate Heat Exposure Index (HEI), Heat Sensitivity Index (HSI), Adapative Capability Index (ACI).
    2. Apply normalisation and quintile operation to determine overall heat vulnerability index.
    3. Upload GUHVI data to PostgreSQL database.
    """
    print(
        '\nGenerating Global Urban Heat Vulnerability Index (GUHVI) indicators',
    )

    # Fetch urban study region data
    (
        urban_study_region_gdf,
        urban_study_region_1600m_gdf,
    ) = get_study_region_gdfs(r)

    # Build compact Earth Engine feature collections with simplified study region boundary;
    # The original GeoDataFrames remain available for exact post-download masking.
    (
        urban_study_region_fc,
        urban_study_region_1600m_fc,
    ) = get_study_region_ee_feature_collections(
        urban_study_region_gdf,
        urban_study_region_1600m_gdf,
    )

    # Convert to geometry objects
    geometry = urban_study_region_fc.geometry(1)
    geometry_1600m = urban_study_region_1600m_fc.geometry(1)

    # Simplify geometries to reduce vertex count
    geometry = geometry.simplify(maxError=100)
    geometry_1600m = geometry_1600m.simplify(maxError=100)
    bounding_box_1600m = geometry_1600m.bounds()

    # Define target year from config file
    target_year = r.config['year']

    # Define the spatial resolution at 1km (1000m)
    guhvi_scale = 1000

    # Fetch coordinate reference system (CRS) from config file
    crs_metric = r.config['crs_srid']
    srid_int = int(crs_metric.split(':')[1])

    # The default 1 km GUHVI grid is too coarse for small or fragmented study
    # regions: reduceRegion/reduceRegions sample pixels by centroid, so a
    # sub-kilometre or scattered geometry can fall entirely between 1 km grid
    # cells, yielding null quintile thresholds and empty output tables even when
    # the bounding box spans several square kilometres.  Downscale the analysis
    # grid for small regions so they still produce valid GUHVI results.
    small_region_threshold_km2 = 25
    fine_guhvi_scale = 100
    region_area_km2 = (
        urban_study_region_gdf.to_crs(crs_metric).area.sum() / 1e6
    )
    if region_area_km2 < small_region_threshold_km2:
        guhvi_scale = fine_guhvi_scale
        print(
            f'Study region area ({region_area_km2:.2f} km²) is below the '
            f'{small_region_threshold_km2} km² threshold; using a finer '
            f'{guhvi_scale} m GUHVI analysis grid so this small/fragmented '
            'region still yields valid results (default is 1 km).',
        )

    # Define function to make uniform grid
    def make_grid(geometry, scale):
        # pixelLonLat returns an image with each pixel labeled with longitude and latitude values
        lonLat = ee.Image.pixelLonLat()

        # Select the longitude and latitude bands, multiply by a large number then truncate them to integers
        lonGrid = lonLat.select('longitude').multiply(10000000).toInt()
        latGrid = lonLat.select('latitude').multiply(10000000).toInt()

        # Multiply the latitude and longitude images and then use reduce to vectors
        grid = lonGrid.multiply(latGrid).reduceToVectors(
            geometry=geometry,
            scale=scale,
            geometryType='polygon',
            crs=crs_metric,
        )

        return grid

    # PREPARE GRID

    # Define geometry with margin error of 1
    geometry_1600m = urban_study_region_1600m_fc.geometry(1)

    # Call function to create 1km x 1km grid
    grid = make_grid(geometry_1600m, guhvi_scale)

    # DEFINE DATA PREPARATION FUNCTIONS

    # Function to change negative/positive sign for NDVI calculation
    def flip_sign(image, band):
        # Select the specific band
        select_band = image.select(band)

        # Multiply the band by -1 to change the sign
        flipped_band = select_band.multiply(-1)

        # Add the modified band as a new band to the original image
        flipped_image = image.addBands(flipped_band.rename('flipped'))

        return flipped_image

    # Function to invert band for LSA calculation
    def invert_band(image, band_name, top_value):
        # Get the specified band
        band = image.select(band_name)

        # Invert the band by subtracting each pixel value from the top value
        inverted_band = ee.Image(top_value).subtract(band)

        # Add the inverted band to the original image
        inverted_image = image.addBands(inverted_band.rename('inverted'))

        return inverted_image

    # Function to remap and convert band based on a new order for LCZ calculation
    def remap_and_convert_band(image, band, new_order):
        # Get band
        original_band = image.select(band)

        # Remap the original band to the custom order
        remapped_band = original_band.remap(list(range(1, 18)), new_order)

        # Add the remapped and converted bands to the image
        remapped_image = image.addBands(
            remapped_band.rename('remapped'),
        ).toInt32()

        return remapped_image

    # CALCULATE HOTTEST THIRD OF THE YEAR (MODIS)
    # https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD11A1

    # Calculate the start and end years using previous target year input
    start_year = target_year - 5

    # Define the start and end dates as strings
    start_date = f"{start_year}-01-01"
    end_date = f"{target_year}-01-01"

    # Load MODIS data and add the Celsius band
    modis_collection = (
        ee.ImageCollection('MODIS/061/MOD11A1')
        .filterDate(start_date, end_date)
        .filterBounds(geometry)
        .select(['LST_Day_1km'])
    )

    # Function to add LST in Celsius as a new band
    def convert_to_celsius(image):
        # Convert LST from Kelvin to Celsius for daytime LST
        lst_day = (
            image.select('LST_Day_1km')
            .multiply(0.02)
            .subtract(273.15)
            .rename('LST')
        )

        # Add the Celsius band to the image
        return image.addBands(lst_day)

    # Apply the function to the image collection
    modis_collection_with_celsius = modis_collection.map(convert_to_celsius)

    # Function to calculate monthly statistics (average of maximum LST for each month over 5 years)
    def calculate_monthly_stat(collection, reducer, month, stat_name):
        # Filter collection to only include images from each month, e.g. all January images from 2019-2024, and then clip to urban study region
        filtered = collection.filter(
            ee.Filter.calendarRange(month, month, 'month'),
        ).map(lambda img: img.clip(urban_study_region_fc))

        # Create a composite image for each month and only retain the pixel with the greatest 'LST' value
        # This essentially returns a composited image for each month where every pixel is attributed with the greatest 'LST' from the past 5 years
        stat_image = filtered.qualityMosaic('LST')

        # Reduce the mosaic image for each month to get the statistical value of mean of maximum LST over 5 years
        lst_stat = (
            stat_image.select('LST')
            .reduceRegion(
                reducer=reducer,
                geometry=geometry,
                scale=guhvi_scale,
                bestEffort=True,
            )
            .get('LST')
        )

        # Add metadata for month and stat value
        return stat_image.set('month', month).set(stat_name, lst_stat)

    # Calculate monthly average LST for each month across the 5-year period
    monthly_mean = ee.List.sequence(1, 12).map(
        lambda m: calculate_monthly_stat(
            modis_collection_with_celsius,
            ee.Reducer.mean(),
            m,
            'mean_lst',
        ),
    )

    # Convert to ImageCollection
    monthly_mean_collection = ee.ImageCollection.fromImages(monthly_mean)

    # Function to calculate 4-month period average (°C) starting from the current month
    def calculate_4month_avg(monthly_lst_values, start_month):
        # Define the four months for the calculation
        months_to_consider = [(start_month + i - 1) % 12 + 1 for i in range(4)]

        # Retrieve the mean LST for each of the four months
        neighbor_values = [
            monthly_lst_values[m - 1]
            for m in months_to_consider
            if monthly_lst_values[m - 1] is not None
        ]

        if not neighbor_values:
            return None, months_to_consider

        # Calculate the average of the four months
        return float(np.mean(neighbor_values)), months_to_consider

    # Print average LST for each month and calculate 4-month period average (°C)
    print('Monthly Mean Max LST and Consecutive 4-Month Period Mean (°C):')
    # Retrieve all twelve monthly means from Earth Engine in a single request
    # (previously one getInfo() per month, plus another per four-month window,
    # each of which re-evaluated the monthly quality mosaics server-side).
    monthly_lst_values = monthly_mean_collection.aggregate_array(
        'mean_lst',
    ).getInfo()

    max_4month_avg = -float('inf')
    max_month_with_neighbors = None

    for month in range(1, 13):
        month_mean_lst = monthly_lst_values[month - 1]
        if month_mean_lst is not None:
            consecutive_4month_avg, months_to_consider = calculate_4month_avg(
                monthly_lst_values,
                month,
            )
            if consecutive_4month_avg is None:
                print(f"Month {month}: No Data")
                continue
            print(
                f"Month {month}: Mean LST = {month_mean_lst:.3f} °C, "
                f"Consecutive 4-Month Period ({', '.join([f'Month {m}' for m in months_to_consider])}) Mean = {consecutive_4month_avg:.3f} °C",
            )
            if consecutive_4month_avg > max_4month_avg:
                max_4month_avg = consecutive_4month_avg
                max_month_with_neighbors = month
        else:
            print(f"Month {month}: No Data")

    # Print the month with maximum Consecutive 4-Month Period Mean
    print(
        f"\nHottest Consecutive 4-Month Period (Hottest Third of the Year) begins with month number {max_month_with_neighbors}, with a mean maximum temperature of {max_4month_avg:.3f} °C",
    )

    # Define the hottest 4-month period based on Consecutive 4-Month Period Mean
    def get_date_range_4_months(center_month, year):
        start_month = center_month
        end_month = (center_month + 4 - 1) % 12 + 1

        start_date = f"{year}-{start_month:02d}-01"
        # Calculate the end month
        if start_month > end_month:
            # Adjust year for end of the period
            end_date = f"{year + 1}-{end_month:02d}-01"
        else:
            end_date = f"{year}-{end_month:02d}-01"

        return start_date, end_date

    # Get window start and end dates for hottest third of the year period
    hottest_start_date, hottest_end_date = get_date_range_4_months(
        max_month_with_neighbors,
        target_year,
    )
    print(
        f"Hottest Third of the Year: Start = {hottest_start_date}, End = {hottest_end_date}",
    )

    # LAND SURFACE TEMPERATURE (LST) - LANDSAT-8 SR

    # Function to mask clouds from Landsat 8 Collection 2, Level 2
    def mask_landsat8_sr_clouds(image):
        qa_mask = image.select('QA_PIXEL').bitwiseAnd(int('11111', 2)).eq(0)
        saturation_mask = image.select('QA_RADSAT').eq(0)

        optical_bands = image.select('SR_B.*').multiply(0.0000275).add(-0.2)
        thermal_bands = image.select('ST_B.*').multiply(0.00341802).add(149.0)

        return (
            image.addBands(optical_bands, None, True)
            .addBands(thermal_bands, None, True)
            .updateMask(qa_mask)
            .updateMask(saturation_mask)
        )

    # Map the function over the hottest third of the year
    landsat_sr_collection = (
        ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
        .filterDate(hottest_start_date, hottest_end_date)
        .filterBounds(bounding_box_1600m)
        .map(mask_landsat8_sr_clouds)
    )

    # Calculate LST
    def calculate_lst(image):
        st = image.select('ST_B10')
        lst = st.subtract(273.15).rename('LST')
        return image.addBands(lst)

    # Create a collection attributed with LST data
    collection_with_lst = landsat_sr_collection.map(calculate_lst)

    # Calculate the overall average LST for the 12 monthly maximums
    mean_lst = collection_with_lst.select('LST').mean()

    # Clip the LST image to the cityBoundary
    lst_clipped = mean_lst.clip(urban_study_region_fc)

    # LAND SURFACE ALBEDO (LSA) - LANDSAT-8 TOA

    # Define the mask Landsat function
    def mask_landsat8_toa_clouds(image):
        qa = image.select('QA_PIXEL')
        mask = qa.bitwiseAnd(1 << 3).eq(0)
        return image.updateMask(mask)

    # Define the albedo function
    def albedo(image):
        alb = image.expression(
            '((0.356*blue)+(0.130*red)+(0.373*nir)+(0.085*swir)+(0.072*swir2)- 0.018)/ 1.016',
            {
                'blue': image.select('B2'),
                'red': image.select('B4'),
                'nir': image.select('B5'),
                'swir': image.select('B6'),
                'swir2': image.select('B7'),
            },
        )
        return image.addBands(alb.rename('albedo'))

    # Load Landsat 8 TOA collection, apply the albedo function, and filter by date and region
    landsat_toa_collection = (
        ee.ImageCollection('LANDSAT/LC08/C02/T1_TOA')
        .filterDate(hottest_start_date, hottest_end_date)
        .filterBounds(bounding_box_1600m)
        .map(mask_landsat8_toa_clouds)
        .map(albedo)
    )

    # Select only the albedo band and calculate the mean
    albedo_mean = landsat_toa_collection.select('albedo').mean()

    # Clip to city
    lsa_clipped = albedo_mean.clip(urban_study_region_fc)

    # NORMALISED DIFFERENCE VEGETATION INDEX (NDVI) - SENTINEL-2 SR

    # Function to mask clouds in Sentinel-2 imagery
    def mask_s2_clouds(image):
        qa = image.select('QA60')
        cloud_mask = 1 << 10
        cirrus_mask = 1 << 11
        mask = (
            qa.bitwiseAnd(cloud_mask)
            .eq(0)
            .And(qa.bitwiseAnd(cirrus_mask).eq(0))
        )
        return (
            image.updateMask(mask)
            .divide(10000)
            .select(['B.*'])
            .copyProperties(image, ['system:time_start'])
        )

    # Load Sentinel-2 SR data using dates for the hottest month of the year
    sentinel_collection_hottest_period = (
        ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterBounds(bounding_box_1600m)
        .filterDate(hottest_start_date, hottest_end_date)
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 90))
        .map(mask_s2_clouds)
    )

    # Calculate NDVI
    def calculate_ndvi(image):
        nir = image.select('B8')
        red = image.select('B4')
        ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI')
        return image.addBands(ndvi)

    # Apply NDVI calculation to the image collection
    sentinel_hottest_period_collection_ndvi = (
        sentinel_collection_hottest_period.map(calculate_ndvi)
    )

    # Calculate mean NDVI
    hottest_period_ndvi = sentinel_hottest_period_collection_ndvi.select(
        'NDVI',
    ).mean()

    # Clip the NDVI image to the city boundary
    ndvi_clipped = hottest_period_ndvi.clip(urban_study_region_fc)

    # NORMALISED DIFFERENCE BUILT-UP INDEX (NDBI) - SENTINEL-2 SR

    # Calculate NDBI
    def calculate_ndbi(image):
        swir = image.select('B11')
        nir = image.select('B8')
        ndbi = swir.subtract(nir).divide(swir.add(nir)).rename('NDBI')
        return image.addBands(ndbi)

    # Apply NDBI calculation to the image collection
    sentinel_hottest_period_collection_ndbi = (
        sentinel_collection_hottest_period.map(calculate_ndbi)
    )

    # Calculate mean NDBI
    hottest_period_ndbi = sentinel_hottest_period_collection_ndbi.select(
        'NDBI',
    ).mean()

    # Clip the NDBI image to the city boundary
    ndbi_clipped = hottest_period_ndbi.clip(urban_study_region_fc)

    # LOCAL CLIMATE ZONES (LCZ)
    # https://developers.google.com/earth-engine/datasets/catalog/RUB_RUBCLIM_LCZ_global_lcz_map_latest

    # Create an ImageCollection and mosaic it, restricted to the tiles that
    # intersect the study region (only those can contribute pixels within it).
    dataset = (
        ee.ImageCollection(
            'RUB/RUBCLIM/LCZ/global_lcz_map/latest',
        )
        .filterBounds(geometry)
        .mosaic()
    )

    # Clip to the specified region
    lcz_clipped = dataset.clip(urban_study_region_fc)

    # Only select relevant band
    lcz_cleaned = lcz_clipped.select('LCZ_Filter')

    # POPULATION DENSITY (POPD) - GHS Population Grid, Epoch 2025, 1km Resolution, Mollweide EPSG:54009
    # https://human-settlement.emergency.copernicus.eu/download.php?ds=pop

    # Define a dictionary to store FeatureCollections for various data
    ghs_pop = ee.Image('projects/ee-global-indicators/assets/GUHVI/POPD')

    # Clip the image to the specified city
    ghs_pop_clipped = ghs_pop.clip(urban_study_region_fc)

    # Rename the band
    ghs_pop_clipped = ghs_pop_clipped.rename('ghs_pop')

    # VULNERABLE POPULATION (POPV) - generated from WorldPop
    # https://developers.google.com/earth-engine/datasets/catalog/WorldPop_GP_100m_pop_age_sex_cons_unadj

    # Load WorldPop data, restricted to the tiles intersecting the study
    # region (only those can contribute to the mosaic within it, so this does
    # not change results but avoids mapping over the entire global collection).
    world_pop_dataset_popv = ee.ImageCollection(
        'WorldPop/GP/100m/pop_age_sex_cons_unadj',
    ).filterBounds(geometry)

    # Custom function to calculate percentage of vulnerable population and append it as a new attribute
    def add_percent_popv(image):
        # Select relevant age groups of 4- and 65+ for both sexes
        vulnerable_age_group = [
            'M_0',
            'M_1',
            'M_65',
            'M_70',
            'M_75',
            'M_80',
            'F_0',
            'F_1',
            'F_65',
            'F_70',
            'F_75',
            'F_80',
        ]

        # Calculate the sum of vulnerable population for each pixel
        vulnerable_pop_sum = image.select(vulnerable_age_group).reduce(
            ee.Reducer.sum(),
        )

        # Calculate the total population
        total_population = image.select('population')

        # Calculate the percentage of vulnerable population for each pixel
        percent_vulnerable_pop = (
            vulnerable_pop_sum.divide(total_population)
            .multiply(100)
            .rename('percent_popv')
        )

        # Add the new band to the image
        image_with_vulnerable_pop = image.addBands(percent_vulnerable_pop)

        return image_with_vulnerable_pop

    # Map the custom function over the dataset
    image_with_popv = (world_pop_dataset_popv.map(add_percent_popv)).mosaic()

    # Select relevant bands
    image_with_popv_relevant_bands = image_with_popv.select('percent_popv')

    # Clip the mean image to the city boundary
    popv_clipped = image_with_popv_relevant_bands.clip(urban_study_region_fc)

    # Create a mask for non-zero values
    popv_non_zero_mask = popv_clipped.neq(0)

    # Apply the mask to popv_clipped
    popv_clipped_non_zero = popv_clipped.updateMask(popv_non_zero_mask)

    # CHILD DEPENDENCY RATIO (CDR) - generated from WorldPop
    # https://developers.google.com/earth-engine/datasets/catalog/WorldPop_GP_100m_pop_age_sex_cons_unadj

    # Load WorldPop data, restricted to the tiles intersecting the study
    # region (see note above).
    world_pop_dataset_cdr = ee.ImageCollection(
        'WorldPop/GP/100m/pop_age_sex_cons_unadj',
    ).filterBounds(geometry)

    # Custom function to calculate percentage of vulnerable population and append it as a new attribute
    def add_child_dependecy_ratio(image):
        # Select relevant age groups for both men and women
        child_age_group = [
            'M_0',
            'M_1',
            'M_5',
            'M_10',
            'F_0',
            'F_1',
            'F_5',
            'F_10',
        ]

        working_age_group = [
            'M_15',
            'M_20',
            'M_25',
            'M_30',
            'M_35',
            'M_40',
            'M_45',
            'M_50',
            'M_55',
            'M_60',
            'F_15',
            'F_20',
            'F_25',
            'F_30',
            'F_35',
            'F_40',
            'F_45',
            'F_50',
            'F_55',
            'F_60',
        ]

        # Calculate the sum of young age group for each pixel
        child_age_sum = image.select(child_age_group).reduce(ee.Reducer.sum())

        # Calculate the sum of working age group for each pixel
        working_age_sum = image.select(working_age_group).reduce(
            ee.Reducer.sum(),
        )

        # Calculate the total population
        total_population = image.select('population')

        # Calculate percentage of total
        child_age_percent = child_age_sum.divide(total_population)

        # Calculate percentage of total
        working_age_percent = working_age_sum.divide(total_population)

        # Calculate the child dependency ratio for each pixel
        child_dependency_ratio = (
            child_age_percent.divide(working_age_percent)
            .multiply(100)
            .rename('child_dependency_ratio')
        )

        # Add the new rounded band to the image
        cdr_image = image.addBands(
            child_dependency_ratio.rename('child_dependency_ratio'),
        )

        return cdr_image

    # Map the custom function over the dataset
    image_with_cdr = (
        world_pop_dataset_cdr.map(add_child_dependecy_ratio)
    ).mosaic()

    # Select relevant bands
    image_with_cdr_relevant_bands = image_with_cdr.select(
        'child_dependency_ratio',
    )

    # Clip the mean image to the city boundary
    cdr_clipped = image_with_cdr_relevant_bands.clip(urban_study_region_fc)

    # Create a mask for non-zero values
    cdr_non_zero_mask = cdr_clipped.neq(0)

    # Apply the mask to cdr_clipped
    cdr_clipped_non_zero = cdr_clipped.updateMask(cdr_non_zero_mask)

    # DEFINE SHDI & IMR DATA INPUTS

    # Load files from Earth Engine public storage
    shdi = ee.Image('projects/ee-global-indicators/assets/GUHVI/SHDI')
    imr = ee.Image('projects/ee-global-indicators/assets/GUHVI/IMR')

    # SUBNATIONAL HUMAN DEVELOPMENT INDEX (SHDI)

    # Clip the SHDI FeatureCollection to the specified city
    shdi_clipped = shdi.clip(urban_study_region_fc)

    # INFANT MORTALITY RATES (IMR)

    # Clip the IMR FeatureCollection to the specified city
    imr_clipped = imr.clip(urban_study_region_fc)

    # LOCAL CLIMATE ZONES (LCZ): remap the LCZ_Filter band from least to most
    # heat retaining before normalisation (its min/max is computed together
    # with the other layers below).

    # List from 1-17 to include all climate zones
    original_order = [
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
    ]

    # Modify custom_order from least heat retaining to most heat retaining,
    # following the LCZ band order described in the RUBCLIM global LCZ map
    # dataset documentation.
    custom_order = [17, 11, 12, 13, 14, 9, 6, 16, 7, 4, 5, 10, 8, 1, 3, 2, 15]

    def generate_new_order(original_order, custom_order):
        # Initialize an empty list to store the new order
        new_order = []

        # Iterate over each element in the original order
        for element in original_order:
            # Find the index of the element in custom_order
            index_in_custom_order = custom_order.index(element)

            # Append the index position to new_order (incremented by 1)
            new_order.append(index_in_custom_order + 1)

        return new_order

    # Generate new_order using the function and remap/convert the band
    lcz_new_order = generate_new_order(original_order, custom_order)
    lcz_remapped_converted = remap_and_convert_band(
        lcz_cleaned,
        'LCZ_Filter',
        lcz_new_order,
    )

    # ------------------------------------------------------------------
    # Build the raw GUHVI layer bands in Earth Engine, download them to a
    # local multi-band GeoTIFF in one request, then derive the per-cell
    # statistics, coastline overlap, normalisation, composites and quintiles
    # locally.
    #
    # Sampling every output grid cell on the server (reduceRegions) repeatedly
    # hit Earth Engine's ~5 minute on-demand compute ceiling, and computing the
    # coastline overlap band server-side - intersecting every grid cell with the
    # unioned global coastline polygons - was an O(cells x coastline) operation
    # that ran for hours.  Both the zonal statistics and the overlap are cheap
    # local operations, so the raw bands are downloaded once and everything
    # downstream is computed on disk.
    # ------------------------------------------------------------------
    lsa_inverted = invert_band(lsa_clipped, 'albedo', 1)
    ndvi_flipped = flip_sign(ndvi_clipped, 'NDVI')

    # The raw bands that back the output tables, in the order Earth Engine
    # writes them to the GeoTIFF.  The image is unmasked to a sentinel over the
    # whole download region so masked pixels can be excluded locally (a
    # downloaded GeoTIFF does not reliably record Earth Engine's mask).
    GUHVI_DOWNLOAD_NODATA = -9999.0
    GUHVI_DOWNLOAD_SCALE = 100
    raw_band_names = [
        'LST',
        'albedo',
        'inverted',
        'NDVI',
        'flipped',
        'NDBI',
        'LCZ_Filter',
        'remapped',
        'ghs_pop',
        'percent_popv',
        'child_dependency_ratio',
        'shdi',
        'imr',
    ]
    raw_band_image = (
        ee.Image.cat(
            [
                lst_clipped.select('LST'),
                lsa_inverted.select(['albedo', 'inverted']),
                ndvi_flipped.select(['NDVI', 'flipped']),
                ndbi_clipped.select('NDBI'),
                lcz_remapped_converted.select(['LCZ_Filter', 'remapped']),
                ghs_pop_clipped.select('ghs_pop'),
                popv_clipped_non_zero.select('percent_popv'),
                cdr_clipped_non_zero.select('child_dependency_ratio'),
                shdi_clipped.select('b1').rename('shdi'),
                imr_clipped.select('b1').rename('imr'),
            ],
        )
        .unmask(GUHVI_DOWNLOAD_NODATA, False)
        .toFloat()
    )

    # Download at a finer resolution than the output grid and aggregate to the
    # grid locally: a direct 1 km download would resample by nearest neighbour,
    # whereas the values the tables must reproduce are the mean of the finer
    # pixels within each cell (as reduceRegions previously computed).
    clean_city = clean_city_name_for_gee(r.config['name'])
    out_dir = os.path.join(r.config['region_dir'], 'guhvi_tiles')
    os.makedirs(out_dir, exist_ok=True)
    out_tif = os.path.join(
        out_dir,
        f'GHSCI_GUHVI_Raster_{clean_city}_{GUHVI_DOWNLOAD_SCALE}m_'
        f'{target_year}.tif',
    )

    if os.path.exists(out_tif):
        print(
            f'\nReusing previously downloaded GUHVI raster '
            f'{out_tif.replace("/home/ghsci/", "")}...',
        )
    else:
        minx, miny, maxx, maxy = urban_study_region_gdf.total_bounds
        est_bytes = (
            ((maxx - minx) / GUHVI_DOWNLOAD_SCALE)
            * ((maxy - miny) / GUHVI_DOWNLOAD_SCALE)
            * 4
            * len(raw_band_names)
        )
        download_gee_geotiff(
            image=raw_band_image,
            out_tif=out_tif,
            region=geometry_1600m,
            scale=GUHVI_DOWNLOAD_SCALE,
            crs=crs_metric,
            est_bytes=est_bytes,
            label='GUHVI',
        )

    # Fetch the output grid once and convert it to a local metric GeoDataFrame
    # (its geometry and cell labels match the previous pipeline).
    grid_gdf = gpd.GeoDataFrame.from_features(
        grid.getInfo()['features'],
        crs='EPSG:4326',
    ).to_crs(crs_metric)
    grid_gdf['label'] = grid_gdf['label'].astype('int64')

    with rasterio.open(out_tif) as src:
        raster_transform = src.transform
        raster_shape = (src.height, src.width)

    # Rasterise the grid cell labels onto the downloaded raster once, then
    # derive every band's per-cell mean from it.
    grid_labels = rasterise_band_labels(
        grid_gdf.geometry,
        raster_transform,
        raster_shape,
    )
    cell_means = zonal_means_by_band(
        out_tif,
        raw_band_names,
        grid_labels,
        GUHVI_DOWNLOAD_NODATA,
        len(grid_gdf),
        # No GUHVI band legitimately falls below this (the lowest is LST in
        # degrees Celsius, around -60); it removes sentinel pixels partially
        # mixed with valid values during resampling.
        valid_floor=-1000.0,
    )

    # Coastline overlap per grid cell from the same global OSM water polygons
    # asset used previously.  The polygons are clipped to the buffered study
    # region server-side (a single ocean polygon would otherwise be downloaded
    # in full), then rasterised so the overlap is the fraction of each cell not
    # covered by water.
    water_polygons = (
        ee.FeatureCollection(
            'projects/ee-global-indicators/assets/GUHVI/'
            'OpenStreetMap_GlobalCoastlines',
        )
        .filterBounds(geometry_1600m)
        .map(lambda feature: feature.intersection(geometry_1600m, 1))
    )
    water_gdf = gpd.GeoDataFrame.from_features(
        water_polygons.getInfo()['features'],
        crs='EPSG:4326',
    )
    if len(water_gdf) > 0:
        water_gdf = water_gdf.to_crs(crs_metric)
    else:
        water_gdf = gpd.GeoDataFrame(geometry=[], crs=crs_metric)
    water_mask = rasterise_binary(
        water_gdf.geometry,
        raster_transform,
        raster_shape,
    )
    overlap_percentage = overlap_percentage_by_cell(
        water_mask,
        grid_labels,
        len(grid_gdf),
    )

    # Layer specification:
    #   (name, downloaded/raw bands, band used for normalisation, normalisation kind)
    layer_specs = [
        ('lst', ['LST'], 'LST', 'standard'),
        ('lsa', ['albedo', 'inverted'], 'inverted', 'standard'),
        ('ndvi', ['NDVI', 'flipped'], 'flipped', 'ndxi'),
        ('ndbi', ['NDBI'], 'NDBI', 'ndxi'),
        ('lcz', ['LCZ_Filter', 'remapped'], 'remapped', 'lcz'),
        ('popd', ['ghs_pop'], 'ghs_pop', 'standard'),
        ('popv', ['percent_popv'], 'percent_popv', 'nulls'),
        ('cdr', ['child_dependency_ratio'], 'child_dependency_ratio', 'nulls'),
        ('shdi', ['shdi'], 'shdi', 'standard'),
        ('imr', ['imr'], 'imr', 'standard'),
    ]

    # Output table column names, where they differ from the downloaded band
    # names.  SHDI and IMR both expose their value as 'b1' downstream (see
    # indicators-ee.yml), but their bands are renamed on download to avoid the
    # name collision between the two single-band source assets.
    table_band_names = {'shdi': ['b1'], 'imr': ['b1']}

    # Layers that are min-max normalised from their in-region values; CDR,
    # SHDI and IMR use fixed 0-100 ranges.
    guhvi_layers_with_minmax = {
        'lst',
        'lsa',
        'ndvi',
        'ndbi',
        'lcz',
        'popd',
        'popv',
    }

    # The previous min/max statistics were reduced over the urban study region
    # boundary rather than the buffered extent, so restrict the local
    # statistics to grid cells whose representative point lies in the region.
    region_geometry = unary_union(
        urban_study_region_gdf.to_crs(crs_metric).geometry,
    )
    in_study_region = grid_gdf.geometry.representative_point().within(
        region_geometry,
    ).to_numpy()

    layer_min_max = {}
    for name, _raw_bands, band, _kind in layer_specs:
        if name in guhvi_layers_with_minmax:
            values = cell_means[band][in_study_region]
            valid = np.isfinite(values)
            if valid.any():
                layer_min_max[name] = (
                    float(values[valid].min()),
                    float(values[valid].max()),
                )
            else:
                layer_min_max[name] = (0.0, 100.0)
        else:
            layer_min_max[name] = (0.0, 100.0)

    def guhvi_to_db(r, name, gdf):
        # Reproject the GeoDataFrame to local coordinate reference system
        gdf = gdf.to_crs(crs_metric)

        # Identify LCZ columns and final GUHVI_class which need to remain as whole numbers
        integer_columns = {'LCZ_Filter', 'remapped', 'GUHVI_class'}
        band_columns = [col for col in gdf.columns if col != 'geometry']

        # Add hottest dates to LST table only
        if name == 'lst':
            gdf['hottest_start_date'] = hottest_start_date
            gdf['hottest_end_date'] = hottest_end_date
            band_columns.extend(['hottest_start_date', 'hottest_end_date'])

            column_defs = [
                (
                    f"{col} INTEGER"
                    if col in integer_columns
                    else (
                        f"{col} TEXT"
                        if col in ['hottest_start_date', 'hottest_end_date']
                        else f"{col} FLOAT"
                    )
                )
                for col in band_columns
            ]
        else:
            column_defs = [
                f"{col} INTEGER" if col in integer_columns else f"{col} FLOAT"
                for col in band_columns
            ]

        # SQL to create table
        create_table_sql = f"""
        DROP TABLE IF EXISTS guhvi_{name};
        CREATE TABLE guhvi_{name} (
            id SERIAL PRIMARY KEY,
            {",\n        ".join(column_defs)},
            geom GEOMETRY(Geometry, {srid_int})
        );
        """

        # SQL to insert data
        insert_sql = f"""
        INSERT INTO guhvi_{name} ({", ".join(band_columns)}, geom)
        VALUES ({", ".join([f":{col}" for col in band_columns])}, ST_SetSRID(ST_GeomFromText(:geom), {srid_int}));
        """

        # Build all row parameter dictionaries up-front and insert them in a
        # single executemany call: issuing one INSERT per row is markedly
        # slower for the large GUHVI output grids.
        params = [
            {
                **{
                    col: (
                        int(row[col])
                        if col in integer_columns
                        else (
                            str(row[col])
                            if name == 'lst'
                            and col
                            in ['hottest_start_date', 'hottest_end_date']
                            else float(row[col])
                        )
                    )
                    for col in band_columns
                },
                'geom': row['geometry'].wkt,
            }
            for _, row in gdf.iterrows()
        ]

        # Execute
        with r.engine.begin() as conn:
            conn.execute(text(create_table_sql))
            if params:
                conn.execute(text(insert_sql), params)

    # Normalise every layer locally and write the per-layer tables.
    def _normalise_values(values, orig_min, orig_max, overlap, kind):
        # Reproduces the previous server-side expressions:
        #   standard/ndxi/nulls: clamp((value-min)/(max-min) * 100 * overlap/100)
        #   lcz:                 clamp((value-min)/(max-min) * overlap)
        # (nulls additionally map missing values to 0 before masking).
        #
        # Earth Engine's divide returns 0 for division by 0, so a layer whose
        # in-region values are all equal (e.g. the WorldPop constrained age
        # structure, which is spatially uniform) normalises to 0 rather than
        # producing NaN.  Reproduce that here, while keeping NaN for cells with
        # no data so they are still dropped.
        denominator = orig_max - orig_min
        finite = np.isfinite(values)
        if denominator == 0:
            scaled = np.where(finite, 0.0, np.nan)
        else:
            with np.errstate(invalid='ignore', divide='ignore'):
                scaled = (values - orig_min) / denominator
        if kind == 'lcz':
            normalised = scaled * overlap
        else:
            normalised = scaled * 100.0 * (overlap / 100.0)
        normalised = np.clip(normalised, 0.0, 100.0)
        if kind == 'nulls':
            normalised = np.where(finite, normalised, 0.0)
        return normalised

    # Per-cell normalised component values, keyed by grid-cell label, used to
    # reconstruct the equal-weighted HEI/HSI/ACI/GUHVI composites below.
    cell_data = {}
    grid_labels_array = grid_gdf['label'].to_numpy()
    grid_geometries = grid_gdf.geometry.to_numpy()

    print('Computing GUHVI component layers locally...')
    for name, raw_bands, band, kind in layer_specs:
        print(f'Processing {name}...')
        orig_min, orig_max = layer_min_max[name]
        normalised = _normalise_values(
            cell_means[band],
            orig_min,
            orig_max,
            overlap_percentage,
            kind,
        )

        output_bands = table_band_names.get(name, raw_bands)
        columns = {
            table_band: cell_means[source_band]
            for table_band, source_band in zip(output_bands, raw_bands)
        }
        columns['normalised_band'] = normalised
        columns['overlap_percentage'] = overlap_percentage

        layer_gdf = gpd.GeoDataFrame(
            columns,
            geometry=grid_geometries,
            crs=crs_metric,
        )

        # Retain only rows with valid data in every band of this layer
        # (matching the previous per-layer server-side notNull filter).
        valid = (
            layer_gdf[output_bands + ['normalised_band']]
            .notna()
            .all(axis=1)
            .to_numpy()
        )
        if not valid.any():
            print(
                f"  No '{name}' GUHVI features intersected the "
                f'{guhvi_scale} m output grid for this study region; '
                'skipping this table.',
            )
            continue

        # Record the per-cell normalised value (keyed by the grid-cell label)
        # for the local reconstruction of the HEI/HSI/ACI/GUHVI composites.
        # Only cells that are valid for this layer contribute (so a masked
        # component does not contribute a spurious 0), matching the previous
        # server-side notNull filter.
        for position in np.nonzero(valid)[0]:
            rec = cell_data.setdefault(int(grid_labels_array[position]), {})
            rec['geom'] = grid_geometries[position]
            rec[name] = float(normalised[position])

        guhvi_to_db(r, name, layer_gdf[valid])

    # Reconstruct the HEI, HSI, ACI and final GUHVI equal-weighted composites
    # per grid cell from the per-layer normalised cell means.  These composite
    # layers are arithmetic means of their components, so the per-cell composite
    # value equals the mean of the per-cell component values (for cells with
    # full component coverage).  Doing this locally means no single heavy Earth
    # Engine request ever has to compute the full GUHVI composite --- the source
    # of the "Computation timed out" errors --- and the {p20, p40, p60, p80}
    # quintile thresholds are then computed locally as well.
    hei_components = ['lst']
    hsi_components = ['lsa', 'ndvi', 'ndbi', 'lcz', 'popd', 'popv']
    aci_components = ['cdr', 'shdi', 'imr']

    def _mean_of(rec, components):
        values = [rec[c] for c in components if rec.get(c) is not None]
        if not values:
            return None
        return float(np.mean(values))

    composite_rows = []
    for rec in cell_data.values():
        hei_value = _mean_of(rec, hei_components)
        hsi_value = _mean_of(rec, hsi_components)
        aci_value = _mean_of(rec, aci_components)
        guhvi_parts = [
            value for value in (hei_value, hsi_value, aci_value)
            if value is not None
        ]
        if not guhvi_parts:
            continue
        composite_rows.append(
            {
                'geom': rec['geom'],
                'hei': hei_value,
                'hsi': hsi_value,
                'aci': aci_value,
                'equal_weighted_average': float(np.mean(guhvi_parts)),
            },
        )

    # Safety net: if no grid cell produced a computable GUHVI value, advise the
    # user and skip GUHVI rather than generating empty tables.
    if not composite_rows:
        print(
            '\nWarning: no valid GUHVI pixel data was found within the study '
            'region, so GUHVI indicators will not be generated for this study '
            'region. Skipping GUHVI analysis and continuing.',
        )
        return

    # Local quintile thresholds and five-class classification of the final
    # GUHVI composite (classes match the previous server-side expression).
    guhvi_values = [row['equal_weighted_average'] for row in composite_rows]
    p80, p60, p40, p20 = np.percentile(guhvi_values, [80, 60, 40, 20])
    print(
        f'GUHVI quintile thresholds (computed locally): '
        f'p20 = {p20:.3f}, p40 = {p40:.3f}, p60 = {p60:.3f}, '
        f'p80 = {p80:.3f}',
    )

    def _classify(value):
        if value > p80:
            return 5
        if value > p60:
            return 4
        if value > p40:
            return 3
        if value > p20:
            return 2
        return 1

    for row in composite_rows:
        row['GUHVI_class'] = _classify(row['equal_weighted_average'])

    def _composite_gdf(rows, source_key):
        data = [
            (row[source_key], row['geom'])
            for row in rows
            if row.get(source_key) is not None
        ]
        return gpd.GeoDataFrame(
            {'equal_weighted_average': [value for value, _ in data]},
            geometry=[geom for _, geom in data],
            crs=crs_metric,
        )

    guhvi_to_db(r, 'hei', _composite_gdf(composite_rows, 'hei'))
    guhvi_to_db(r, 'hsi', _composite_gdf(composite_rows, 'hsi'))
    guhvi_to_db(r, 'aci', _composite_gdf(composite_rows, 'aci'))
    guhvi_to_db(
        r,
        'guhvi',
        gpd.GeoDataFrame(
            {
                'equal_weighted_average': [
                    row['equal_weighted_average'] for row in composite_rows
                ],
                'GUHVI_class': [row['GUHVI_class'] for row in composite_rows],
            },
            geometry=[row['geom'] for row in composite_rows],
            crs=crs_metric,
        ),
    )

    print(
        '\nGlobal Urban Heat Vulnerability Index (GUHVI) indicators complete',
    )


def earth_engine_analysis(r):
    initialize_gee()
    lpugs_analysis(r)
    guhvi_analysis(r)
