"""
Generate Google Earth Engine Indicators:
1. Large Public Urban Green Space (LPUGS)
2. Global Urban Heat Vulnerability Index (GUHVI)
"""

import time
import json
import os

import ee
import geemap

import pandas as pd
import geopandas as gpd
import pandana as pdna
import numpy as np
import osmnx as ox
import networkx as nx
from shapely import wkt
from shapely.ops import substring
from shapely.geometry import Point, LineString

import rasterio
from rasterio.mask import mask
from rasterio.io import MemoryFile

import psycopg2
from sqlalchemy import text
from sqlalchemy import create_engine

import ghsci
import requests

from setup_sp import create_pdna_net, cal_dist_node_to_nearest_pois


def initialize_gee():
    """Initialize Google Earth Engine using the quota_project_id from the Google Cloud credentials file."""
    # Path to Google Cloud credentials
    adc_path = os.path.expanduser('~/.config/gcloud/application_default_credentials.json')
    
    try:
        # Try to read the quota_project_id from credentials file
        with open(adc_path, 'r') as f:
            credentials = json.load(f)
            project_id = credentials.get('quota_project_id')
            
            if project_id:
                print(f"Initializing Earth Engine with project: {project_id}")
                ee.Initialize(project=project_id)
            else:
                print("No project id found in saved credentials file.")
        return project_id
    
    except Exception as e:
        print(f"Error initializing Earth Engine: {str(e)}")
        raise


def get_gdf(
    r: ghsci.Region,
    table_name: str,
    columns: str = "*",
    geom_col: str = "geom",
    where_clause: str = "",
    index_col: str | list | None = None,
    rename_cols: dict | None = None,
) -> gpd.GeoDataFrame:
    """
    Fetch data from PostgreSQL as GeoDataFrame.

    """
    # Build the SQL query
    query = f"""
    SELECT {columns}
    FROM {table_name}
    {f"WHERE {where_clause}" if where_clause else ""}
    """
    
    # Execute query
    with r.engine.connect() as connection:
        gdf = gpd.read_postgis(
            query,
            connection,
            geom_col=geom_col,
            index_col=index_col
        )
    
    # Apply column renaming if specified
    if rename_cols:
        gdf = gdf.rename(columns=rename_cols)
    
    return gdf


def lpugs_analysis(r):
    """
    1. Identify LPUGS overall greenery and upload raster to PostgreSQL database
    2. Identify LPUGS availability as a subset of areas of open space and upload to PostgreSQL database
    3. Perform network analysis to determine LPUGS accessibility within 500m
    4. Overlap population grid with accessible network service area to determine service area and upload to PostgreSQL database
    
    """
    print("\nGenerating Large Public Urban Green Space (LPUGS) availability and accessibility indicators")
    
    # Initialize Google Earth Engine and get project_id
    project_id = initialize_gee()
    if not project_id:
        raise ValueError("Could not initialize Google Earth Engine - no project ID found")
    
    # LPUGS OVERALL GREENERY
    
    # Fetch urban study region data
    urban_study_region_gdf = get_gdf(r, "urban_study_region")
    urban_study_region_1600m_gdf = get_gdf(r, "urban_study_region_1600m")
    
    # Convert GeoDataFrame to ee.FeatureCollection
    urban_study_region_fc = geemap.gdf_to_ee(urban_study_region_gdf, geodesic=False)
    urban_study_region_1600m_fc = geemap.gdf_to_ee(urban_study_region_1600m_gdf, geodesic=False)
    
    # Fetch the target year and define date range
    target_year = r.config['year']
    start_date = f"{target_year}-01-01"
    end_date = f"{target_year + 1}-01-01"

    # Get the bounding box of urban study region 1600m for Sentinel NDVI data
    bounding_box_1600m = urban_study_region_1600m_fc.geometry().bounds()

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
            .select(["B.*"])
            .copyProperties(image, ["system:time_start"])
        )

    # Function to calculate NDVI
    def calculate_ndvi(image):
        ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
        return image.addBands(ndvi)

    # Load Sentinel-2 imagery, mask clouds, and calculate NDVI
    sentinel_collection = (
        ee.ImageCollection("COPERNICUS/S2_HARMONIZED")
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
        .rename('NDVI') # Ensure attribute name is maintained
    )

    # Filter to only retain NDVI ≥ 0.2 and clip to urban study region
    filtered_ndvi = (
        mean_ndvi
        .updateMask(mean_ndvi.gte(0.2))
        .clip(urban_study_region_1600m_fc)
    )
    
    # Fetch city name and remove whitespaces, for example: 'Porto Alegre' -> 'PortoAlegre'
    city = r.config["name"]
    clean_city = city.replace(" ", "")
    
    # Define asset upload path using cleaned city name
    lpugs_ndvi_asset_path = f'projects/{project_id}/assets/temp_lpugs_raster_{clean_city}'

    # Get the geometry of the study region for raster clip
    geometry = urban_study_region_fc.geometry()
    
    # Convert ee.Image to GeoTIFF raster at 100m resolution
    export_task = ee.batch.Export.image.toAsset(
        image=filtered_ndvi,
        description=f'GHSCI_LPUGS_Raster_{clean_city}',
        assetId=lpugs_ndvi_asset_path,
        scale=50, # Sentinel's native 10m resolution results in enormous file sizes, especially for large cities. Exporting at 50m maintains balance between high-resolution spatial insight, data size, and processing speeds
        region=geometry,
        crs='EPSG:3857',
        maxPixels=1e13
    )
    export_task.start()
    print("LPUGS Availability raster upload task started. Waiting for completion...")

    # Wait for export completion with timeout
    max_wait_time = 10800  # 3 hour timeout
    wait_interval = 30
    elapsed_time = 0
    
    # Print statements to log file to track progress
    while export_task.active() and elapsed_time < max_wait_time:
        time.sleep(wait_interval)
        elapsed_time += wait_interval
        print(f"Waiting... {elapsed_time}s elapsed")

    if export_task.status()['state'] != 'COMPLETED':
        print("LPUGS Availability raster upload complete...")
        raise Exception(f"GEE export failed after {elapsed_time}s: {export_task.status()}")

    # Download GeoTIFF from GEE
    print("Downloading GeoTIFF from Google Earth Engine...")
    download_params = {
        'name': f'GHSCI_LPUGS_Raster_{clean_city}_download',
        'scale': 50,
        'region': geometry,
        'crs': 'EPSG:3857',
        'filePerBand': False,
        'format': 'GEO_TIFF'
    }

    try:
        download_url = filtered_ndvi.getDownloadURL(download_params)
        response = requests.get(download_url, timeout=10800) # 3 hour timeout
        response.raise_for_status()
    except Exception as e:
        raise Exception(f"Failed to download GeoTIFF: {str(e)}")
    
    # Reproject urban study region geometry to EPSG:3857 for clip
    urban_study_region_gdf_reprojected = urban_study_region_gdf.to_crs(3857)

    # Get WKT representation of the urban study region
    urban_study_region_wkt = urban_study_region_gdf_reprojected.geometry.iloc[0].wkt

    # Load the downloaded raster into memory
    with MemoryFile(response.content) as memfile:
        with memfile.open() as src:
            # Prepare the mask geometry
            mask_geom = wkt.loads(urban_study_region_wkt)
            
            # Convert to GeoJSON format for rasterio
            geoms = [mask_geom.__geo_interface__]

            # Get the mask and window
            mask_shape, mask_transform, mask_window = rasterio.mask.raster_geometry_mask(
                src, 
                geoms,
                invert=True,  # Invert so area inside geometry is kept
                crop=True     # Crop to the extent of the geometry
            )
            
            if mask_window is None:
                raise ValueError("Geometry does not intersect with raster")
                
            # Read the data using the window
            data = src.read(window=mask_window)
            
            # Apply the mask to nullify outside pixels with value -9999 and create output array
            out_image = np.full_like(data, src.nodata or -9999)
            
            # Only copy pixels within the mask
            for band in range(out_image.shape[0]):
                out_image[band][mask_shape] = data[band][mask_shape]
            
            # Get the transform for the clipped area
            out_transform = src.window_transform(mask_window)
            
            # Update metadata
            out_meta = src.meta.copy()
            out_meta.update({
                "driver": "GTiff",
                "height": mask_window.height,
                "width": mask_window.width,
                "transform": out_transform,
                "nodata": src.nodata or -9999  # Ensure nodata value is set
            })
            
            # Write the clipped raster to a new memory file
            with MemoryFile() as clipped_memfile:
                with clipped_memfile.open(**out_meta) as dst:
                    dst.write(out_image)
                
                # Get the bytes of the clipped raster
                clipped_raster_bytes = clipped_memfile.read()

    # Upload raster to PostgreSQL database
    class PostgresRasterUploader:
        def __init__(self, db_config):
            self.db_config = db_config
            self.engine = self._create_engine()
            
        def _create_engine(self):
            """Create SQLAlchemy engine with connection pooling"""
            return create_engine(
                f'postgresql://{self.db_config["user"]}:{self.db_config["password"]}'
                f'@{self.db_config["host"]}/{self.db_config["database"]}',
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False)
            )
        
        def upload_raster(self, table_name, raster_data):
            """Upload raster data to PostgreSQL with proper JSON handling"""
            import json
            
            metadata = {
                'source': 'Google Earth Engine',
                'resolution': '50m',
                'crs': 'EPSG:3857',
                'ndvi_threshold': 0.2
            }

            with self.engine.begin() as conn:
                conn.execute(text(f"""
                    DROP TABLE IF EXISTS {table_name};
                    CREATE TABLE {table_name} (
                        id SERIAL PRIMARY KEY,
                        rast raster,
                        acquisition_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        metadata JSONB
                    )
                """))
                
                conn.execute(text(f"""
                    INSERT INTO {table_name} (rast, metadata) 
                    VALUES (
                        ST_FromGDALRaster(:raster_data),
                        (:metadata)::jsonb
                    )
                """), {
                    'raster_data': raster_data,
                    'metadata': json.dumps(metadata)
                })

    db_config = {
        'host': r.config['db_host'],
        'database': r.config['db'],
        'user': r.config['db_user'],
        'password': r.config['db_pwd']
    }

    uploader = PostgresRasterUploader(db_config)
    uploader.upload_raster(
        table_name='lpugs_overall_greenery',
        raster_data=clipped_raster_bytes
    )

    print("Successfully uploaded NDVI data to PostgreSQL")
    
    # Delete the GEE asset
    print("Deleting GEE asset...")
    ee.data.deleteAsset(lpugs_ndvi_asset_path)
    print(f"Deleted asset: {lpugs_ndvi_asset_path}")
    
    # LPUGS AVAILABILITY
    
    # Fetch areas of open space using geom_public as the geometry
    aos_public_osm_gdf = get_gdf(
        r,
        "aos_public_osm",
        columns="aos_id, aos_ha_public, geom_public as geom"
    )
    
    # Filter in GeoPandas to only include greater than or equal to 1 ha in area and only Polygon geometry type
    aos_public_osm_gdf = aos_public_osm_gdf[
        (aos_public_osm_gdf['aos_ha_public'] >= 1) &
        (aos_public_osm_gdf['geom'].geom_type == 'Polygon')
    ]

    # Convert GeoDataFrame to Earth Engine FeatureCollection
    aos_public_osm_fc = geemap.gdf_to_ee(aos_public_osm_gdf, geodesic=False)

    # Calculate annual average NDVI and clip to AOS features
    annual_average_ndvi_clipped = (
        sentinel_collection.select('NDVI')
        .mean()
        .clip(aos_public_osm_fc)
    )

    # Create a mask for NDVI >= 0.2
    lpugs_mask = annual_average_ndvi_clipped.gte(0.2).rename('LPUGS')

    # Function to add mean NDVI to each feature
    def add_ndvi_to_feature(feature):
        ndvi_value = annual_average_ndvi_clipped.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=feature.geometry(),
            scale=10,
            bestEffort=True,
        ).get('NDVI')

        # Convert to server-side ee.Number and filter for NDVI >= 0.2
        ndvi_num = ee.Number(ndvi_value)
        condition = ndvi_num.gte(0.2)

        # Return the feature only if NDVI >= 0.2, otherwise return None
        return ee.Algorithms.If(
            condition,
            feature.set({'NDVI_mean': ndvi_value}),
            None
        )

    # Function to calculate NDVI >= 0.2 area in hectares
    def calculate_ndvi_area(feature):
        ndvi_area = (
            lpugs_mask.multiply(ee.Image.pixelArea())
            .reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=feature.geometry(),
                scale=10,
                bestEffort=True,
            )
            .get('LPUGS')
        )
        return feature.set(
            {'NDVI_ha': ee.Number(ndvi_area).divide(1e4)} # Convert to hectares
        )

    # Add NDVI to filtered AOS features
    lpugs_fc = aos_public_osm_fc.map(add_ndvi_to_feature, dropNulls=True)

    # Filter out null features
    lpugs_w_ndvi = lpugs_fc.filter(ee.Filter.notNull(['NDVI_mean']))

    # Apply the area calculation
    lpugs_fc = lpugs_w_ndvi.map(calculate_ndvi_area)
    
    # Convert ee.FeatureCollection to GeoDataFrame
    # First, try to directly convert using geemap's ee_to_gdf
    # A single query to Earth Engine is limited to 10MB in size so success of this method depends on the size of the feature collection.
    try:
        print("Attempting direct conversion with geemap.ee_to_gdf...")
        lpugs_gdf = geemap.ee_to_gdf(lpugs_fc)
        
    except Exception as e:
        # Upload as a GEE Asset
        print(f"Direct conversion failed: {str(e)}. Falling back to GEE asset export method...")
        
        # Define the GEE asset path for the feature collection
        lpugs_fc_asset_path = f'projects/{project_id}/assets/temp_lpugs_features_{clean_city}'

        try:
            # Export the FeatureCollection to GEE Asset
            export_task = ee.batch.Export.table.toAsset(
                collection=lpugs_fc,
                description=f'GHSCI_LPUGS_FeatureCollection_{clean_city}',
                assetId=lpugs_fc_asset_path,
            )
            export_task.start()
            print("Export task started. Waiting for completion...")

            # Wait for export completion
            max_wait_time = 10800  # 3 hour timeout
            wait_interval = 30
            elapsed_time = 0
            
            # Print statements to log file to track progress
            while export_task.active() and elapsed_time < max_wait_time:
                time.sleep(wait_interval)
                elapsed_time += wait_interval
                print(f"Waiting... {elapsed_time}s elapsed")

            if export_task.status()['state'] != 'COMPLETED':
                print("LPUGS features upload complete...")
                raise Exception(f"GEE export failed after {elapsed_time}s: {export_task.status()}")
            
            # Now fetch the asset from the cloud and directly convert to GeoDataFrame
            print("Converting ee.FeatureCollection to GeoDataFrame...")
            lpugs_fc_local = ee.FeatureCollection(lpugs_fc_asset_path)
            lpugs_gdf = geemap.ee_to_gdf(lpugs_fc_local)

            # Delete the GEE asset
            print("Deleting GEE asset...")
            ee.data.deleteAsset(lpugs_fc_asset_path)
            print(f"Deleted asset: {lpugs_fc_asset_path}")

        except Exception as e:
            # For extremely large LPUGS feature collections a batch upload method is necessary
            print(f"Single asset export failed: {str(e)}. Falling back to batched upload method...")
            
            # Implement batch upload approach with tiny batches
            initial_batch_size = 500
            batch_size = initial_batch_size
            batch_gdfs = []
            processed_features = 0
            success_count = 0
            max_attempts = 3
            
            while True:  # Break when all features are processed
                attempt = 0
                batch_success = False
                
                while attempt < max_attempts and not batch_success:
                    try:
                        # Get the current batch
                        current_batch = lpugs_fc.limit(batch_size, processed_features)
                        
                        # Test if we can get info about this batch without downloading
                        test_feature = current_batch.first()
                        test_feature.id().getInfo()  # Small request to test payload size
                        
                        # If we get here, the batch size is acceptable
                        batch_asset_path = f'{lpugs_fc_asset_path}_batch_{processed_features}'
                        
                        # Export batch
                        export_task = ee.batch.Export.table.toAsset(
                            collection=current_batch,
                            description=f'GHSCI_LPUGS_FeatureCollection_{clean_city}_batch_{processed_features}',
                            assetId=batch_asset_path,
                        )
                        export_task.start()
                        print(f"Started export for batch starting at {processed_features} (size: {batch_size})...")
                        
                        # Wait for completion
                        elapsed_time = 0
                        while export_task.active() and elapsed_time < max_wait_time:
                            time.sleep(wait_interval)
                            elapsed_time += wait_interval
                            
                        if export_task.status()['state'] != 'COMPLETED':
                            print(f"Batch export failed: {export_task.status()}")
                            attempt += 1
                            continue
                            
                        # Convert batch to GeoDataFrame
                        batch_fc_local = ee.FeatureCollection(batch_asset_path)
                        batch_gdf = geemap.ee_to_gdf(batch_fc_local)
                        actual_batch_size = len(batch_gdf)
                        
                        if actual_batch_size == 0:
                            print("Reached end of feature collection")
                            batch_success = True
                            break
                            
                        batch_gdfs.append(batch_gdf)
                        processed_features += actual_batch_size
                        success_count += 1
                        batch_success = True
                        
                        # Delete GEE Asset
                        ee.data.deleteAsset(batch_asset_path)
                        print(f"Successfully processed batch (size: {actual_batch_size}, total: {processed_features})")
                        
                        # If we've had 3 successes at this batch size, try increasing batch size to speed things up
                        if success_count >= 3 and batch_size < 2000:  # Cap at 2000 features
                            new_batch_size = min(batch_size * 2, 2000)
                            print(f"Increasing batch size from {batch_size} to {new_batch_size}")
                            batch_size = new_batch_size
                            success_count = 0
                        
                    except Exception as batch_e:
                        print(f"Error with batch size {batch_size}: {str(batch_e)}")
                        if "payload size" in str(batch_e):
                            # Reduce batch size if payload too large
                            batch_size = max(1, batch_size // 2)
                            print(f"Reducing batch size to {batch_size}")
                            success_count = 0
                        attempt += 1
                        continue
                
                if not batch_success:
                    print("Failed all attempts to process batch. Aborting.")
                    break
                    
                if actual_batch_size == 0:
                    break
                    
                if attempt >= max_attempts:
                    print("Max attempts reached without success. Aborting.")
                    break
            
            # Combine all successful batches
            if batch_gdfs:
                lpugs_gdf = gpd.concat(batch_gdfs, ignore_index=True)
                print(f"Successfully processed {len(lpugs_gdf)} features")
            else:
                raise Exception("All batch exports failed. Could not process FeatureCollection.")

    # Convert geometry to WKT
    lpugs_gdf['geom'] = lpugs_gdf['geometry'].apply(lambda x: x.wkt)

    # Ensure the GeoDataFrame has the correct CRS before exporting
    crs_metric = r.config['crs_srid']
    srid_int = int(crs_metric.split(':')[1])
    lpugs_gdf = lpugs_gdf.to_crs(srid_int)

    # Upload to PostgreSQL database
    with r.engine.begin() as connection:
        # Drop and create LPUGS table
        connection.execute(text(f"""
            DROP TABLE IF EXISTS large_public_urban_green_space;
            CREATE TABLE large_public_urban_green_space (
                lpugs_id SERIAL PRIMARY KEY,
                aos_id INTEGER,
                aos_ha_public FLOAT,
                NDVI_mean FLOAT,
                NDVI_ha FLOAT,
                geom GEOMETRY(Geometry, %s)
            );
        """ % srid_int))
        
        # Insert data row by row into LPUGS table
        insert_data_sql = """
        INSERT INTO large_public_urban_green_space (aos_id, aos_ha_public, NDVI_mean, NDVI_ha, geom)
        VALUES (:aos_id, :aos_ha_public, :NDVI_mean, :NDVI_ha, ST_Transform(ST_SetSRID(ST_GeomFromText(:geom), 4326), :target_srid));
        """
        
        for _, row in lpugs_gdf.iterrows():
            connection.execute(
                text(insert_data_sql),
                {
                    'aos_id': row['aos_id'],
                    'aos_ha_public': row['aos_ha_public'],
                    'NDVI_mean': row['NDVI_mean'],
                    'NDVI_ha': row['NDVI_ha'],
                    'geom': row['geom'],
                    'target_srid': srid_int
                }
            )
            
        # Whilst we are here, create the lpugs_nodes_30m_line table for LPUGS accessibility network analysis
        connection.execute(text("""
            DROP TABLE IF EXISTS lpugs_nodes_30m_line;
            CREATE TABLE lpugs_nodes_30m_line AS
            SELECT DISTINCT n.*, l.lpugs_id
            FROM aos_public_any_nodes_30m_line n
            JOIN large_public_urban_green_space l ON n.aos_id = l.aos_id;
            
            CREATE INDEX lpugs_nodes_30m_line_gix ON lpugs_nodes_30m_line USING GIST (geom);
        """))
    
    # LPUGS ACCESSIBILITY

    # Fetch network data
    nodes = r.get_gdf('nodes', index_col='osmid')
    nodes.columns = ['geometry' if x == 'geom' else x for x in nodes.columns]
    nodes = nodes.set_geometry('geometry')
    edges = r.get_gdf('edges')
    edges.columns = ['geometry' if x == 'geom' else x for x in edges.columns]
    edges = edges.set_geometry('geometry')
    
    # Create Pandana network
    network = create_pdna_net(nodes, edges, predistance=500)
    
    # Fetch LPUGS nodes
    with r.engine.connect() as connection:
        lpugs_nodes_gdf = gpd.read_postgis(
            """
            SELECT ST_Transform(geom, 4326) AS geom, aos_id, aos_entryid, node, lpugs_id
            FROM lpugs_nodes_30m_line;
            """,
            connection,
            geom_col='geom',
        ).to_crs(crs_metric)

    # Calculate distances from all nodes to nearest LPUGS point
    distances = cal_dist_node_to_nearest_pois(
        gdf_poi=lpugs_nodes_gdf,
        geometry='geom',
        distance=500,
        network=network,
        output_names=['lpugs'],
    )
    
    # Identify accessible nodes (within max_distance) excluding those beyond max distance using -999 as per cal_dist_node_to_nearest_pois function
    accessible_nodes = distances[distances['lpugs'] != -999].index.tolist()
    
    # Filter nodes and edges using the accessible_nodes list
    filtered_nodes = nodes.loc[nodes.index.isin(accessible_nodes)].copy()
    filtered_edges = edges[
        (edges['u'].isin(accessible_nodes)) & 
        (edges['v'].isin(accessible_nodes))
    ].copy()
    
    # Load population grid
    population_grid_gdf = get_gdf(
        r,
        r.config["population_grid"],
        columns="grid_id, pop_est, geom"
    ).to_crs(crs_metric)
    
    # Rename population grid's 'geom' to 'geometry' for the spatial join
    population_grid_for_join = population_grid_gdf.rename_geometry('geometry')
    
    # Create accessibility grid (grid cells intersecting accessible edges)
    lpugs_accessibility_grid = gpd.sjoin(
        population_grid_for_join[['grid_id', 'pop_est', 'geometry']],
        filtered_edges[['geometry']],
        how='inner',
        predicate='intersects',
    )
    
    # Keep only unique grid cells with their population
    lpugs_accessibility_grid = lpugs_accessibility_grid[
        ['grid_id', 'pop_est', 'geometry']
    ].drop_duplicates('grid_id')
    
    # Upload results to database
    with r.engine.begin() as connection:
        # Drop and create tables
        connection.execute(text("DROP TABLE IF EXISTS lpugs_accessible_nodes;"))
        connection.execute(text("DROP TABLE IF EXISTS lpugs_accessible_network;"))
        connection.execute(text("DROP TABLE IF EXISTS lpugs_accessibility_grid;"))

        # Create and populate accessible nodes table
        connection.execute(text(f"""
            CREATE TABLE lpugs_accessible_nodes (
                osmid INT8 PRIMARY KEY,
                x FLOAT,
                y FLOAT,
                geom GEOMETRY(Point, {srid_int})
            );
        """))
        
        if not filtered_nodes.empty:
            filtered_nodes = filtered_nodes.to_crs(srid_int)
            # Add x,y coordinates if not already present
            if 'x' not in filtered_nodes.columns:
                filtered_nodes['x'] = filtered_nodes.geometry.x
            if 'y' not in filtered_nodes.columns:
                filtered_nodes['y'] = filtered_nodes.geometry.y
            
            stmt = text(f"""
                INSERT INTO lpugs_accessible_nodes (osmid, x, y, geom)
                VALUES (:osmid, :x, :y, ST_SetSRID(ST_GeomFromText(:geom), {srid_int}));
            """)
            params = [{
                'osmid': idx,
                'x': row['x'],
                'y': row['y'],
                'geom': row['geometry'].wkt,
            } for idx, row in filtered_nodes.iterrows()]
            connection.execute(stmt, params)

        # Create and populate accessible network table
        connection.execute(text(f"""
            CREATE TABLE lpugs_accessible_network (
                id SERIAL PRIMARY KEY,
                u INT8,
                v INT8,
                key INT8,
                length FLOAT,
                osmid TEXT,
                geom GEOMETRY(LineString, {srid_int})
            );
        """))
        
        if not filtered_edges.empty:
            filtered_edges = filtered_edges.to_crs(srid_int)
            stmt = text(f"""
                INSERT INTO lpugs_accessible_network (u, v, key, length, osmid, geom)
                VALUES (:u, :v, :key, :length, :osmid, ST_SetSRID(ST_GeomFromText(:geom), {srid_int}));
            """)
            params = [{
                'u': row['u'],
                'v': row['v'],
                'key': row['key'],
                'length': row['length'],
                'osmid': str(row['osmid']),
                'geom': row['geometry'].wkt,
            } for _, row in filtered_edges.iterrows()]
            connection.execute(stmt, params)

        # Create and populate accessibility grid table
        connection.execute(text(f"""
            CREATE TABLE lpugs_accessibility_grid (
                grid_id TEXT PRIMARY KEY,
                pop_est FLOAT,
                geom GEOMETRY(Polygon, {srid_int})
            );
        """))
        
        if not lpugs_accessibility_grid.empty:
            stmt = text(f"""
                INSERT INTO lpugs_accessibility_grid (grid_id, pop_est, geom)
                VALUES (:grid_id, :pop_est, ST_SetSRID(ST_GeomFromText(:geom), {srid_int}));
            """)
            params = [{
                'grid_id': row['grid_id'],
                'pop_est': row['pop_est'],
                'geom': row['geometry'].wkt,
            } for _, row in lpugs_accessibility_grid.iterrows()]
            connection.execute(stmt, params)
    
    print("\nLarge Public Urban Green Space (LPUGS) availability and accessibility indicators complete")


def guhvi_analysis(r):
    """
    1. Generate Heat Exposure Index (HEI), Heat Sensitivity Index (HSI), Adapative Capability Index (ACI).
    2. Apply normalisation and quintile operation to determine overall heat vulnerability index.
    3. Upload GUHVI data to PostgreSQL database.
    
    """
    print("\nGenerating Global Urban Heat Vulnerability Index (GUHVI) indicators")
        
    # Fetch urban study region
    urban_study_region_gdf = get_gdf(r, "urban_study_region")
    urban_study_region_1600m_gdf = get_gdf(r, "urban_study_region_1600m")
    
    # Convert GeoDataFrame to ee.FeatureCollection
    urban_study_region_fc = geemap.gdf_to_ee(urban_study_region_gdf, geodesic=False)
    urban_study_region_1600m_fc = geemap.gdf_to_ee(urban_study_region_1600m_gdf, geodesic=False)
    
    # Get the geometry and bounding box urban study region 1600m
    geometry = urban_study_region_fc.geometry()
    bounding_box_1600m = urban_study_region_1600m_fc.geometry().bounds()
    
    # Define target year from config file
    target_year = r.config['year']

    # Define the spatial resolution at 1km (1000m)
    guhvi_scale = 1000
    
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
            scale=scale, # 1km resolution
            geometryType='polygon',
            crs='EPSG:3857' # Specify EPSG:3857 to ensure a uniform square grid. This is very important!
        )
        
        return grid
    
    # Define a function to create an empty image with an overlap percentage band
    def create_empty_image_with_overlap(grid):
        # Define a function to calculate overlap percentage
        def calculate_overlap_percentage(feature):
            # Extract overlap percentage property
            overlap_percentage = ee.Number(feature.get('overlap_percentage'))
            # Return a feature with overlap percentage band
            return ee.Feature(feature.geometry()).set({'overlap_percentage_band': overlap_percentage})
        
        # Map the function over the grid feature collection
        overlap_with_band = grid.map(calculate_overlap_percentage)
        
        # Convert the feature collection to an image
        overlap_image = overlap_with_band.reduceToImage(properties=['overlap_percentage_band'], reducer=ee.Reducer.first())
        
        # Source image converted to Float64
        source_image = overlap_image.toDouble()
        
        # Convert the source raster image to Float64 and set all values to 1
        float_image = overlap_image.toDouble().multiply(0).add(1)
        
        # Get the projection of the raster image
        image_projection = overlap_image.projection()
        
        # Convert grid to Float64 and set overlap_percentage
        grid_float = overlap_percentage.map(lambda feature: feature.set('overlap_percentage', ee.Number(feature.get('overlap_percentage')).toDouble()))
        
        # Reproject grid to match the projection of the raster image
        grid_reprojected = grid_float.map(lambda feature: feature.transform(image_projection))
        
        # Paint the grid features onto an empty image with 'overlap_percentage' attribute
        painted_image = ee.Image().toDouble().paint(grid_reprojected, 'overlap_percentage')
        
        # Update the mask of the painted image using the original image
        updated_image = painted_image.updateMask(float_image.select(0))
        
        # Add the overlap percentage band to the original image and cast it to Float64
        new_image = ee.Image(source_image.addBands(updated_image.rename('overlap_percentage')))
        
        # Select only the 'overlap_percentage' band
        new_image = new_image.select(['overlap_percentage'])
        
        return new_image
    
    # OCEAN OVERLAP FUNCTION

    # Import global ocean and sea coastline boundaries spatial data
    # Downloaded from https://osmdata.openstreetmap.de/data/water-polygons.html - version stored on GEE public assets was last updated 2nd May 2025
    water_polygons_collection = ee.FeatureCollection('projects/ee-global-indicators/assets/GUHVI/OpenStreetMap_GlobalCoastlines')

    # Filter the water polygons to only include those that intersect with the city boundary
    intersecting_water_bodies = water_polygons_collection.filterBounds(geometry)

    # Merge the intersecting water polygons into a single geometry
    merged_water_body_geometry = intersecting_water_bodies.union().geometry()

    # Convert the geometry to a single feature
    merged_water_body_feature = ee.Feature(merged_water_body_geometry)

    # Define a function to calculate intersection area and overlap percentage
    def calculate_ocean_overlap(feature):
        # Calculate the intersection between the city boundary and the grid square
        intersection = feature.intersection(merged_water_body_feature, maxError=1)
        
        # Check if the intersection is empty
        if intersection is not None:
            # Calculate the area of the grid square
            area = feature.geometry().area(maxError=1)
            
            # Calculate the area of intersection between the grid square and the water
            intersection_area = intersection.area(maxError=1)
            
            # Calculate the percentage area overlap
            overlap_percentage = intersection_area.divide(area).multiply(100)
            
            # Invert the overlap percentage
            inverted_overlap_percentage = ee.Number(100).subtract(overlap_percentage)
            
            # Return the feature with additional properties
            return feature.set({
                'overlap_percentage': inverted_overlap_percentage
            })
        else:
            # If there is no intersection, set overlap properties to 100
            return feature.set({
                'overlap_percentage': 100
            })
            
    # PREPARE GRID

    # Define geometry with margin error of 1
    geometry_1600m = urban_study_region_1600m_fc.geometry(1)

    # Call function to create grid
    grid = make_grid(geometry_1600m, guhvi_scale)

    # Convert grid to a feature collection
    grid_collection = ee.FeatureCollection(grid)

    # Map the function over the grid feature collection
    overlap_percentage = grid.map(calculate_ocean_overlap)

    # Create an empty image with overlap percentage band
    empty_image_with_overlap = create_empty_image_with_overlap(overlap_percentage)

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
        remapped_image = image.addBands(remapped_band.rename('remapped')).toInt32()

        return remapped_image
    
    # DEFINE NORMALISATION FUNCTIONS

    # Function to normalise a given band for LST, LSA, POPD, POPV, SHDI, IMR calculation
    def normalise_band(image, band, original_min, original_max):
        # Select bands of interest
        normalised_image = image.select([band])
        overlap_percentage = image.select(['overlap_percentage'])

        # Define a custom normalisation formula considering overlap_percentage
        normalised_band = normalised_image.expression(
            'clamp(((((value - min) / (max - min)) * 100) * (overlap_percentage / 100)), 0, 100)',
            {
                'value': normalised_image,
                'min': original_min,
                'max': original_max,
                'overlap_percentage': overlap_percentage,
            }
        ).rename('normalised_band')

        # Add the normalised band to the original image as a new band
        result_image = image.addBands(normalised_band)

        return result_image

    # Function to normalise a given band for NDVI and NDBI calculation
    def normalise_band_ndxi(image, band, original_min, original_max):
        # Select bands of interest
        normalised_image = image.select([band])
        overlap_percentage = image.select(['overlap_percentage'])

        # Define a custom normalisation formula considering overlap_percentage
        normalised_band = normalised_image.expression(
            'clamp((((value - (min)) / (max - (min))) * 100) * (overlap_percentage / 100), 0, 100)',
            {
                'value': normalised_image,
                'min': original_min,
                'max': original_max,
                'overlap_percentage': overlap_percentage,
            }
        ).rename('normalised_band')

        # Add the normalised band to the original image as a new band
        result_image = image.addBands(normalised_band)

        return result_image

    # Function to normalise a given band for LCZ calculation
    def normalise_band_lcz(image, band, original_min, original_max):
        # Select bands of interest
        normalised_image = image.select([band])
        overlap_percentage = image.select(['overlap_percentage'])

        # Define a custom normalisation formula considering overlap_percentage
        normalised_band = normalised_image.expression(
            'clamp((((value - min) / (max - min)) * overlap_percentage), 0, 100)',
            {
                'value': normalised_image,
                'min': original_min,
                'max': original_max,
                'overlap_percentage': overlap_percentage,
            }
        ).rename('normalised_band')

        # Add the normalised band to the original image as a new band
        result_image = image.addBands(normalised_band)

        return result_image

    # Function to normalise a given band for CDR calculation
    def normalise_band_nulls(image, band, original_min, original_max):
        # Select bands of interest
        normalised_image = image.select([band])
        overlap_percentage = image.select(['overlap_percentage'])

        # Define a custom normalisation formula considering overlap_percentage
        normalised_band = normalised_image.expression(
            'clamp(((((value - min) / (max - min)) * 100) * (overlap_percentage / 100)), 0, 100)',
            {
                'value': normalised_image,
                'min': original_min,
                'max': original_max,
                'overlap_percentage': overlap_percentage,
            }
        ).rename('normalised_band')
        
        # Replace null values with 0
        normalised_band_masked = (normalised_band.unmask(0)).toDouble()

        # Add the normalised band to the original image as a new band
        result_image = image.addBands(normalised_band_masked)
        
        # Clip to city after filling nulls with 0
        result_image_clipped = result_image.clip(urban_study_region_1600m_fc)

        return result_image_clipped

    # CALCULATE HOTTEST THIRD OF THE YEAR (MODIS)
    # https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD11A1

    # Calculate the start and end years using previous target year input
    start_year = target_year - 5

    # Define the start and end dates as strings
    start_date = f"{start_year}-01-01"
    end_date = f"{target_year}-01-01"

    # Load MODIS data and add the Celsius band
    modis_collection = ee.ImageCollection("MODIS/061/MOD11A1") \
        .filterDate(start_date, end_date)

    # Function to add LST in Celsius as a new band
    def convert_to_celsius(image):
        # Convert LST from Kelvin to Celsius for daytime LST
        lst_day = image.select('LST_Day_1km').multiply(0.02).subtract(273.15).rename('LST')
        
        # Add the Celsius band to the image
        return image.addBands(lst_day)

    # Apply the function to the image collection
    modis_collection_with_celsius = modis_collection.map(convert_to_celsius)

    # Function to calculate monthly statistics (average of maximum LST for each month over 5 years)
    def calculate_monthly_stat(collection, reducer, month, stat_name):
        # Filter collection to only include images from each month, e.g. all January images from 2019-2024, and then clip to urban study region
        filtered = collection.filter(ee.Filter.calendarRange(month, month, 'month')).map(lambda img: img.clip(urban_study_region_fc))
        
        # Create a composite image for each month and only retain the pixel with the greatest 'LST' value
        # This essentially returns a composited image for each month where every pixel is attributed with the greatest 'LST' from the past 5 years
        stat_image = filtered.qualityMosaic('LST')
        
        # Reduce the mosaic image for each month to get the statistical value of mean of maximum LST over 5 years
        lst_stat = stat_image.select('LST').reduceRegion(
            reducer=reducer, geometry=geometry, scale=guhvi_scale, bestEffort=True
        ).get('LST')
        
        # Add metadata for month and stat value
        return stat_image.set('month', month).set(stat_name, lst_stat)

    # Calculate monthly average LST for each month across the 5-year period
    monthly_mean = ee.List.sequence(1, 12).map(lambda m: calculate_monthly_stat(modis_collection_with_celsius, ee.Reducer.mean(), m, 'mean_lst'))

    # Convert to ImageCollection
    monthly_mean_collection = ee.ImageCollection.fromImages(monthly_mean)

    # Function to calculate 4-month period average (°C) starting from the current month
    def calculate_4month_avg(monthly_stats, start_month):
        # Define the four months for the calculation
        months_to_consider = [(start_month + i - 1) % 12 + 1 for i in range(4)]
        
        # Retrieve the mean LST for each of the four months
        neighbor_values = [
            monthly_stats.filter(ee.Filter.eq('month', m)).first().get('mean_lst')
            for m in months_to_consider
        ]
        
        # Calculate the average of the four months
        return ee.Number(ee.List(neighbor_values).reduce(ee.Reducer.mean())), months_to_consider

    # Print average LST for each month and calculate 4-month period average (°C)
    print("Monthly Mean Max LST and Consecutive 4-Month Period Mean (°C):")
    monthly_stats = monthly_mean_collection.toList(12)

    max_4month_avg = -float('inf')
    max_month_with_neighbors = None

    for month in range(1, 13):
        month_data = ee.Image(monthly_stats.get(month - 1))
        month_mean_lst = month_data.get('mean_lst').getInfo()
        if month_mean_lst is not None:
            consecutive_4month_avg, months_to_consider = calculate_4month_avg(monthly_mean_collection, month)
            consecutive_4month_avg = consecutive_4month_avg.getInfo()
            month_names = ', '.join([f"Month {m}" for m in months_to_consider])
            print(f"Month {month}: Mean LST = {month_mean_lst:.3f} °C, "
                f"Consecutive 4-Month Period ({month_names}) Mean = {consecutive_4month_avg:.3f} °C")
            if consecutive_4month_avg > max_4month_avg:
                max_4month_avg = consecutive_4month_avg
                max_month_with_neighbors = month
        else:
            print(f"Month {month}: No Data")

    # Print the month with maximum Consecutive 4-Month Period Mean
    print(f"\nHottest Consecutive 4-Month Period (Hottest Third of the Year) begins with month number {max_month_with_neighbors}, with a mean maximum temperature of {max_4month_avg:.3f} °C")

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
    hottest_start_date, hottest_end_date = get_date_range_4_months(max_month_with_neighbors, target_year)
    print(f"Hottest Third of the Year: Start = {hottest_start_date}, End = {hottest_end_date}") 
    
    # LAND SURFACE TEMPERATURE (LST) - LANDSAT-8 SR

    # Function to mask clouds from Landsat 8 Collection 2, Level 2
    def mask_landsat8_sr_clouds(image):
        qa_mask = image.select('QA_PIXEL').bitwiseAnd(int('11111', 2)).eq(0)
        saturation_mask = image.select('QA_RADSAT').eq(0)

        optical_bands = image.select('SR_B.*').multiply(0.0000275).add(-0.2)
        thermal_bands = image.select('ST_B.*').multiply(0.00341802).add(149.0)

        return image.addBands(optical_bands, None, True) \
            .addBands(thermal_bands, None, True) \
            .updateMask(qa_mask) \
            .updateMask(saturation_mask)

    # Map the function over the hottest third of the year
    landsat_sr_collection = (
        ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
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
            "((0.356*blue)+(0.130*red)+(0.373*nir)+(0.085*swir)+(0.072*swir2)- 0.018)/ 1.016",
            {
                'blue': image.select('B1'),
                'red': image.select('B3'),
                'nir': image.select('B4'),
                'swir': image.select('B5'),
                'swir2': image.select('B7')
            }
        )
        return image.addBands(alb.rename("albedo"))

    # Load Landsat 8 TOA collection, apply the albedo function, and filter by date and region
    landsat_toa_collection = (
        ee.ImageCollection("LANDSAT/LC08/C02/T1_TOA")
        .filterDate(hottest_start_date, hottest_end_date)
        .filterBounds(bounding_box_1600m)
        .map(mask_landsat8_toa_clouds)
        .map(albedo)
    )

    # Select only the albedo band and calculate the mean
    albedo_mean = landsat_toa_collection.select("albedo").mean()

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
            .select(["B.*"])
            .copyProperties(image, ["system:time_start"])
        )

    # Load Sentinel-2 SR data using dates for the hottest month of the year
    sentinel_collection_hottest_period = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
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
    sentinel_hottest_period_collection_ndvi = sentinel_collection_hottest_period.map(calculate_ndvi)

    # Calculate mean NDVI
    hottest_period_ndvi = sentinel_hottest_period_collection_ndvi.select('NDVI').mean()

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
    sentinel_hottest_period_collection_ndbi = sentinel_collection_hottest_period.map(calculate_ndbi)

    # Calculate mean NDBI
    hottest_period_ndbi = sentinel_hottest_period_collection_ndbi.select('NDBI').mean()

    # Clip the NDBI image to the city boundary
    ndbi_clipped = hottest_period_ndbi.clip(urban_study_region_fc)
    
    # LOCAL CLIMATE ZONES (LCZ)
    # https://developers.google.com/earth-engine/datasets/catalog/RUB_RUBCLIM_LCZ_global_lcz_map_latest

    # Create an ImageCollection and mosaic it
    dataset = ee.ImageCollection("RUB/RUBCLIM/LCZ/global_lcz_map/latest").mosaic()

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

    # Load WorldPop data
    world_pop_dataset_popv = ee.ImageCollection("WorldPop/GP/100m/pop_age_sex_cons_unadj")

    # Custom function to calculate percentage of vulnerable population and append it as a new attribute
    def add_percent_popv(image):
        # Select relevant age groups of 4- and 65+ for both sexes
        vulnerable_age_group = ['M_0', 'M_1', 'M_65', 'M_70', 'M_75', 'M_80', 'F_0', 'F_1', 'F_65', 'F_70', 'F_75', 'F_80']
        
        # Calculate the sum of vulnerable population for each pixel
        vulnerable_pop_sum = image.select(vulnerable_age_group).reduce(ee.Reducer.sum())
        
        # Calculate the total population
        total_population = image.select('population')
        
        # Calculate the percentage of vulnerable population for each pixel
        percent_vulnerable_pop = vulnerable_pop_sum.divide(total_population).multiply(100).rename('percent_popv')
        
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

    # Load WorldPop data
    world_pop_dataset_cdr = ee.ImageCollection("WorldPop/GP/100m/pop_age_sex_cons_unadj")

    # Custom function to calculate percentage of vulnerable population and append it as a new attribute
    def add_child_dependecy_ratio(image):
        # Select relevant age groups for both men and women
        child_age_group = ['M_0', 'M_1', 'M_5', 'M_10', 'F_0', 'F_1', 'F_5', 'F_10']
        
        working_age_group = ['M_15', 'M_20', 'M_25', 'M_30', 'M_35', 'M_40', 'M_45', 'M_50', 'M_55', 'M_60',
                            'F_15', 'F_20', 'F_25', 'F_30', 'F_35', 'F_40', 'F_45', 'F_50', 'F_55', 'F_60']
        
        # Calculate the sum of young age group for each pixel
        child_age_sum = image.select(child_age_group).reduce(ee.Reducer.sum())
        
        # Calculate the sum of working age group for each pixel
        working_age_sum = image.select(working_age_group).reduce(ee.Reducer.sum())

        # Calculate the total population
        total_population = image.select('population')

        # Calculate percentage of total
        child_age_percent = child_age_sum.divide(total_population)

        # Calculate percentage of total
        working_age_percent = working_age_sum.divide(total_population)
        
        # Calculate the child dependency ratio for each pixel
        child_dependency_ratio = child_age_percent.divide(working_age_percent).multiply(100).rename('child_dependency_ratio')
        
        # Add the new rounded band to the image
        cdr_image = image.addBands(child_dependency_ratio.rename('child_dependency_ratio'))
        
        return cdr_image

    # Map the custom function over the dataset
    image_with_cdr = (world_pop_dataset_cdr.map(add_child_dependecy_ratio)).mosaic()

    # Select relevant bands
    image_with_cdr_relevant_bands = image_with_cdr.select('child_dependency_ratio')

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
    
    # HEAT EXPOSURE INDEX (HEI) - SUB-INDEX 1

    # Land Surface Temperature (LST) -------------------------------------------------------------------------------------------------

    # Calculate the minimum and maximum values
    min_max_lst = lst_clipped.reduceRegion(
        reducer=ee.Reducer.minMax(),
        geometry=geometry,
        scale=guhvi_scale
    )

    # Extract the min and max values
    min_lst = min_max_lst.getNumber('LST_min')
    max_lst = min_max_lst.getNumber('LST_max')

    # Copy band 'overlap_percentage'
    lst_overlap_image = lst_clipped.addBands(empty_image_with_overlap.select(['overlap_percentage'])).toDouble()
    # Define the known range and input band for each input before normalisation and inversion
    lst_input_original_min = min_lst
    lst_input_original_max = max_lst
    lst_input_band = 'LST'
    # Normalise
    lst_normalised_image = normalise_band(lst_overlap_image, lst_input_band, lst_input_original_min, lst_input_original_max)

    # Perform Equal Weighting & Create HEI -------------------------------------------------------------------------------------------

    # Calculate the equal-weighted average of normalised values for each pixel
    # Since HEI only has one input the values will remain unchanged, however, still perform this step since it will remove the now unnecessary 'LST' and 'overlap_percentage' bands
    hei_equal_weighted_average_image = ee.Image.cat([
        lst_normalised_image.select('normalised_band'),
    ]).reduce(ee.Reducer.mean()).rename('equal_weighted_average')

    # Clip the classified image to the specified geometry
    hei_equal_weighted_average_image_clipped = hei_equal_weighted_average_image.clip(urban_study_region_fc)
    
    # HEAT SENSITIVITY INDEX (HSI) - SUB-INDEX 2

    # Land Surface Albedo (LSA) ------------------------------------------------------------------------------------------------------

    # Invert band
    lsa_inverted = invert_band(lsa_clipped, 'albedo', 1)

    # Calculate the minimum and maximum values
    min_max_lsa = lsa_inverted.reduceRegion(
        reducer=ee.Reducer.minMax(),
        geometry=geometry,
        scale=guhvi_scale
    )

    min_lsa = min_max_lsa.getNumber('inverted_min')
    max_lsa = min_max_lsa.getNumber('inverted_max')

    # Copy band 'overlap_percentage'
    lsa_overlap_image = lsa_inverted.addBands(empty_image_with_overlap.select(['overlap_percentage'])).toDouble()
    # Define the known range and input band for each input before normalisation
    lsa_input_original_min = min_lsa
    lsa_input_original_max = max_lsa
    lsa_input_band = 'inverted'
    # Normalise
    lsa_normalised_image = normalise_band(lsa_overlap_image, lsa_input_band, lsa_input_original_min, lsa_input_original_max)

    # Normalised Difference Vegetation Index (NDVI) ----------------------------------------------------------------------------------

    # Flip negative and positive signs to effectively invert since high NDVI infers lower heat vulnerability
    ndvi_flipped = flip_sign(ndvi_clipped, 'NDVI')

    # Calculate the minimum and maximum values
    min_max_ndvi = ndvi_flipped.reduceRegion(
        reducer=ee.Reducer.minMax(),
        geometry=geometry,
        scale=guhvi_scale
    )

    min_ndvi = min_max_ndvi.getNumber('flipped_min')
    max_ndvi = min_max_ndvi.getNumber('flipped_max')

    # Copy band 'overlap_percentage'
    ndvi_overlap_image = ndvi_flipped.addBands(empty_image_with_overlap.select(['overlap_percentage'])).toDouble()
    # Define the known range and input band for each input before normalisation
    ndvi_input_original_min = min_ndvi
    ndvi_input_original_max = max_ndvi
    ndvi_input_band = 'flipped'
    # Normalise
    ndvi_normalised_image = normalise_band_ndxi(ndvi_overlap_image, ndvi_input_band, ndvi_input_original_min, ndvi_input_original_max)

    # Normalised Difference Built-Up Index (NDBI) ------------------------------------------------------------------------------------

    # Calculate the minimum and maximum values
    min_max_ndbi = ndbi_clipped.reduceRegion(
        reducer=ee.Reducer.minMax(),
        geometry=geometry,
        scale=guhvi_scale
    )

    min_ndbi = min_max_ndbi.getNumber('NDBI_min')
    max_ndbi = min_max_ndbi.getNumber('NDBI_max')

    # Copy band 'overlap_percentage'
    ndbi_overlap_image = ndbi_clipped.addBands(empty_image_with_overlap.select(['overlap_percentage'])).toDouble()
    # Define the known range and input band for each input before normalisation
    ndbi_input_original_min = min_ndbi
    ndbi_input_original_max = max_ndbi
    ndbi_input_band = 'NDBI'
    # Normalise
    ndbi_normalised_image = normalise_band_ndxi(ndbi_overlap_image, ndbi_input_band, ndbi_input_original_min, ndbi_input_original_max)

    # Local Climate Zones (LCZ) ------------------------------------------------------------------------------------------------------

    # List from 1-17 to include all climate zones
    original_order = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]

    # Modify custom_order from least heat retaining to most heat retaining based on order shown here
    # https://developers.google.com/earth-engine/datasets/catalog/RUB_RUBCLIM_LCZ_global_lcz_map_latest#bands
    custom_order = [17, 11, 12, 13, 14, 9, 6, 16, 7, 4, 5, 10, 8, 1, 3, 2, 15]

    def generate_new_order(original_order, custom_order):
        # Initialize an empty list to store the new order
        new_order = []
        
        # Iterate over each element in the original order
        for element in original_order:
            # Find the index of the element in custom_order
            index_in_custom_order = custom_order.index(element)
            
            # Append the index position to new_order (incremented by 1 as per your specification)
            new_order.append(index_in_custom_order + 1)
        
        return new_order

    # Generate new_order using the function
    lcz_new_order = generate_new_order(original_order, custom_order)
    # Remap and convert band
    lcz_remapped_converted = remap_and_convert_band(lcz_cleaned, 'LCZ_Filter', lcz_new_order)

    # Calculate the minimum and maximum values
    min_max_lcz = lcz_remapped_converted.reduceRegion(
        reducer=ee.Reducer.minMax(),
        geometry=geometry,
        scale=guhvi_scale
    )

    min_lcz = min_max_lcz.getNumber('remapped_min')
    max_lcz = min_max_lcz.getNumber('remapped_max')

    # Copy band 'overlap_percentage'
    lcz_overlap_image = lcz_remapped_converted.addBands(empty_image_with_overlap.select(['overlap_percentage'])).toDouble()
    # Define the known range and input band for each input before normalisation
    lcz_input_original_min = min_lcz
    lcz_input_original_max = max_lcz
    lcz_input_band = 'remapped'
    # Normalise
    lcz_normalised_image = normalise_band_lcz(lcz_overlap_image, lcz_input_band, lcz_input_original_min, lcz_input_original_max)

    # Pop Density (POPD) -------------------------------------------------------------------------------------------------------------

    # Calculate the minimum and maximum values
    min_max_popd = ghs_pop_clipped.reduceRegion(
        reducer=ee.Reducer.minMax(),
        geometry=geometry,
        scale=guhvi_scale
    )

    min_popd = min_max_popd.getNumber('ghs_pop_min')
    max_popd = min_max_popd.getNumber('ghs_pop_max')

    # Copy band 'overlap_percentage'
    popd_overlap_image = ghs_pop_clipped.addBands(empty_image_with_overlap.select(['overlap_percentage'])).toDouble()
    # Define the known range and input band for each input before normalisation
    popd_input_original_min = min_popd
    popd_input_original_max = max_popd
    popd_band = 'ghs_pop'
    # Normalise
    popd_normalised_image = normalise_band(popd_overlap_image, popd_band, popd_input_original_min, popd_input_original_max)

    # Vulnerable Pop (POPV) ----------------------------------------------------------------------------------------------------------

    # Calculate the minimum and maximum values
    min_max_popv = popv_clipped_non_zero.reduceRegion(
        reducer=ee.Reducer.minMax(),
        geometry=geometry,
        scale=guhvi_scale
    )

    min_popv = min_max_popv.getNumber('percent_popv_min')
    max_popv = min_max_popv.getNumber('percent_popv_max')

    # Copy band 'overlap_percentage'
    popv_overlap_image = popv_clipped_non_zero.addBands(empty_image_with_overlap.select(['overlap_percentage'])).toDouble()
    # Define the known range and input band for each input before normalisation
    popv_input_original_min = min_popv
    popv_input_original_max = max_popv
    popv_band = 'percent_popv'
    # Normalise
    popv_normalised_image = normalise_band_nulls(popv_overlap_image, popv_band, popv_input_original_min, popv_input_original_max)

    # Perform Equal Weighting & Create HSI -------------------------------------------------------------------------------------------

    # Calculate the equal-weighted average of normalised values for each pixel
    hsi_equal_weighted_average_image = ee.Image.cat([
        lsa_normalised_image.select('normalised_band'),
        ndvi_normalised_image.select('normalised_band'),
        ndbi_normalised_image.select('normalised_band'),
        lcz_normalised_image.select('normalised_band'),
        popd_normalised_image.select('normalised_band'),
        popv_normalised_image.select('normalised_band'),
    ]).reduce(ee.Reducer.mean()).rename('equal_weighted_average')

    # Clip the classified image to the specified geometry
    hsi_equal_weighted_average_image_clipped = hsi_equal_weighted_average_image.clip(urban_study_region_fc)
    
    # ADAPTIVE CAPABILITY INDEX (ACI) - SUB-INDEX 3

    # Child Dependency Ratio (CDR) ---------------------------------------------------------------------------------------------------

    # Copy band 'overlap_percentage'
    cdr_overlap_image = cdr_clipped_non_zero.addBands(empty_image_with_overlap.select(['overlap_percentage'])).toDouble()
    # Define the known range and input band for each input before normalisation
    cdr_input_original_min = 0
    cdr_input_original_max = 100
    cdr_input_band = 'child_dependency_ratio'
    # Normalise
    cdr_normalised_image = normalise_band_nulls(cdr_overlap_image, cdr_input_band, cdr_input_original_min, cdr_input_original_max)

    # Subnational Human Development Index (SHDI) -------------------------------------------------------------------------------------

    # Copy band 'overlap_percentage'
    shdi_overlap_image = shdi_clipped.addBands(empty_image_with_overlap.select(['overlap_percentage'])).toDouble()
    # Define the known range and input band for each input before normalisation
    shdi_input_original_min = 0
    shdi_input_original_max = 100
    shdi_input_band = 'b1'
    # Normalise
    shdi_normalised_image = normalise_band(shdi_overlap_image, shdi_input_band, shdi_input_original_min, shdi_input_original_max)

    # Infant Mortality Rates (IMR) ---------------------------------------------------------------------------------------------------

    # Copy band 'overlap_percentage'
    imr_overlap_image = imr_clipped.addBands(empty_image_with_overlap.select(['overlap_percentage'])).toDouble()
    # Define the known range and input band for each input before normalisation
    imr_input_original_min = 0
    imr_input_original_max = 100
    imr_input_band = 'b1'
    # Normalise
    imr_normalised_image = normalise_band(imr_overlap_image, imr_input_band, imr_input_original_min, imr_input_original_max)

    # Perform Equal Weighting & Create ACI -------------------------------------------------------------------------------------------

    # Calculate the equal-weighted average of normalised values for each pixel
    aci_equal_weighted_average_image = ee.Image.cat([
        cdr_normalised_image.select('normalised_band'),
        shdi_normalised_image.select('normalised_band'),
        imr_normalised_image.select('normalised_band'),
    ]).reduce(ee.Reducer.mean()).rename('equal_weighted_average')

    # Clip the classified image to the specified geometry
    aci_equal_weighted_average_image_clipped = aci_equal_weighted_average_image.clip(urban_study_region_fc)
    
    # CREATE EQUAL WEIGHTED GUHVI IMAGE

    # Calculate the equal-weighted average of normalised values for each pixel
    guhvi_image = ee.Image.cat([
        hei_equal_weighted_average_image_clipped,
        hsi_equal_weighted_average_image_clipped,
        aci_equal_weighted_average_image_clipped,
    ]).reduce(ee.Reducer.mean()).rename('equal_weighted_average')

    # Clip the classified image to the specified geometry (city)
    guhvi_image_clipped = guhvi_image.clip(urban_study_region_fc)
    
    # CREATE GUHVI WITH QUINTILES

    # Calculate quintiles
    quintile_values = guhvi_image_clipped.reduceRegion(
        reducer=ee.Reducer.percentile([20, 40, 60, 80]),
        geometry=geometry,
        scale=guhvi_scale
    )

    # Get the percentile values as ee.Number objects
    p20 = ee.Number(quintile_values.get('equal_weighted_average_p20'))
    p40 = ee.Number(quintile_values.get('equal_weighted_average_p40'))
    p60 = ee.Number(quintile_values.get('equal_weighted_average_p60'))
    p80 = ee.Number(quintile_values.get('equal_weighted_average_p80'))

    # Create a classified image using server-side operations
    classified_image = guhvi_image_clipped.expression(
        '(val <= p20) ? 1 : ' +
        '(val <= p40) ? 2 : ' +
        '(val <= p60) ? 3 : ' +
        '(val <= p80) ? 4 : 5',
        {
            'val': guhvi_image_clipped.select('equal_weighted_average'),
            'p20': p20,
            'p40': p40,
            'p60': p60,
            'p80': p80
        }
    )

    # Add GUHVI index band
    guhvi = guhvi_image_clipped.addBands(classified_image.rename('GUHVI_class').toInt()).toDouble()
    
    # Clip the classified image to the specified geometry (city)
    guhvi_clipped = guhvi.clip(urban_study_region_fc)

    def raster_to_vector_by_grid(raster, grid, scale):
        band_names = raster.bandNames()

        # Use reduceRegions to extract all bands
        vectors = raster.reduceRegions(
            collection=grid,
            reducer=ee.Reducer.mean().forEach(band_names),
            scale=scale,
        )

        # Filter out features that don't have valid data in any band
        valid_vectors = vectors.filter(ee.Filter.notNull(band_names))

        return valid_vectors
    
    raster_list = [
        ('lst', lst_normalised_image),
        ('hei', hei_equal_weighted_average_image_clipped),
        ('lsa', lsa_normalised_image),
        ('ndvi', ndvi_normalised_image),
        ('ndbi', ndbi_normalised_image),
        ('lcz', lcz_normalised_image),
        ('popd', popd_normalised_image),
        ('popv', popv_normalised_image),
        ('hsi', hsi_equal_weighted_average_image_clipped),
        ('cdr', cdr_normalised_image),
        ('shdi', shdi_normalised_image),
        ('imr', imr_normalised_image),
        ('aci', aci_equal_weighted_average_image_clipped),
        ('guhvi', guhvi_clipped),
    ]

    def upload_guhvi_data(r, name, gdf):
        # Reproject the GeoDataFrame to EPSG:3857
        gdf = gdf.to_crs("EPSG:3857")
        
        # Identify LCZ columns and final GUHVI_class which need to remain as whole numbers
        integer_columns = {'LCZ_Filter', 'remapped', 'GUHVI_class'}
        band_columns = [col for col in gdf.columns if col != 'geometry']
        
        # Generate proper column definitions
        column_defs = []
        for col in band_columns:
            col_type = "INTEGER" if col in integer_columns else "FLOAT"
            column_defs.append(f"{col} {col_type}")
        
        # SQL to create table
        create_table_sql = f"""
        DROP TABLE IF EXISTS guhvi_{name};
        CREATE TABLE guhvi_{name} (
            id SERIAL PRIMARY KEY,
            {",\n        ".join(column_defs)},
            geom GEOMETRY(Geometry, 3857)
        );
        """
        
        # SQL to insert data
        insert_sql = f"""
        INSERT INTO guhvi_{name} ({", ".join(band_columns)}, geom)
        VALUES ({", ".join([f":{col}" for col in band_columns])}, ST_SetSRID(ST_GeomFromText(:geom), 3857));
        """

        # Execute
        with r.engine.begin() as conn:
            conn.execute(text(create_table_sql))
            for _, row in gdf.iterrows():
                data = {
                    **{col: int(row[col]) if col in integer_columns else float(row[col]) 
                    for col in band_columns},
                    'geom': row['geometry'].wkt
                }
                conn.execute(text(insert_sql), data)
    
    for name, raster in raster_list:
        print(f"Processing {name}...")
        vector = raster_to_vector_by_grid(raster, grid_collection, guhvi_scale)
        gdf = geemap.ee_to_gdf(vector)
        gdf.columns = [col.replace(':', '_').replace(' ', '_') for col in gdf.columns]
        gdf = gdf.drop(columns=[col for col in ['count', 'label'] if col in gdf.columns])
        upload_guhvi_data(r, name, gdf)
    
    print("\nGlobal Urban Heat Vulnerability Index (GUHVI) indicators complete")


def earth_engine_analysis(r):
    lpugs_analysis(r)
    guhvi_analysis(r)
    