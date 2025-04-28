"""
Identify large public urban green space (LPUGS) through use of the Google Earth Engine API
"""
import sys
import time

# Import Earth Engine and Google Earth Engine Map libraries
import ee
import geemap
import psycopg2
import geopandas as gpd

# import getpass
from script_running_log import script_running_log
from sqlalchemy import text

import ghsci


def fetch_lpugs_data_as_gdf(r: ghsci.Region) -> tuple:
    """Fetch urban study region and AOS public OSM data as GeoDataFrames."""
    # Fetch urban study region data
    with r.engine.connect() as connection:
        urban_study_region_gdf = gpd.read_postgis(
            """
            SELECT ST_Transform(geom, 4326) AS geom
            FROM urban_study_region;
            """,
            connection,
            geom_col='geom',
        )
        
    # Fetch AOS public OSM data
    with r.engine.connect() as connection:
        aos_public_osm_gdf = gpd.read_postgis(
            """
            SELECT ST_Transform(geom, 4326) AS geom, aos_id, aos_ha_public
            FROM aos_public_osm;
            """,
            connection,
            geom_col='geom',
        )
        
    return urban_study_region_gdf, aos_public_osm_gdf


def generate_and_upload_lpugs(codename, r):
    """Generate LPUGS data and upload it directly to the database using SQL queries."""
    # Fetch data for the region
    urban_study_region_gdf, aos_public_osm_gdf = fetch_lpugs_data_as_gdf(r)
    
    # Initialize Google Earth Engine
    project_id = r.config['gee_project_id']
    ee.Initialize(project=project_id)

    # Convert GeoDataFrames to Earth Engine FeatureCollections
    urban_study_region_fc = geemap.gdf_to_ee(urban_study_region_gdf, geodesic=False)
    aos_public_osm_fc = geemap.gdf_to_ee(aos_public_osm_gdf, geodesic=False)
    
    # Filter AOS features larger than 1 hectare
    aos_public_osm_filtered_1ha = aos_public_osm_fc.filter(ee.Filter.gte('aos_ha_public', 1))
    
    # Define the target year and date range
    target_year = r.config['year']
    start_date = f"{target_year}-01-01"
    end_date = f"{target_year + 1}-01-01"

    # Get the bounding box of the study region
    bounding_box = urban_study_region_fc.geometry().bounds()
    
    # Function to mask clouds in Sentinel-2 imagery
    def mask_s2_clouds(image):
        qa = image.select('QA60')
        cloud_mask = 1 << 10
        cirrus_mask = 1 << 11
        mask = qa.bitwiseAnd(cloud_mask).eq(0).And(qa.bitwiseAnd(cirrus_mask).eq(0))
        return image.updateMask(mask).divide(10000).select(["B.*"]).copyProperties(image, ["system:time_start"])

    # Function to calculate NDVI
    def calculate_ndvi(image):
        ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
        return image.addBands(ndvi)
    
    # Load Sentinel-2 imagery, mask clouds, and calculate NDVI
    sentinel_collection = ee.ImageCollection('COPERNICUS/S2_HARMONIZED') \
        .filterBounds(bounding_box) \
        .filterDate(start_date, end_date) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 90)) \
        .map(mask_s2_clouds) \
        .map(calculate_ndvi)
    
    # Calculate annual average NDVI
    annual_average_ndvi = sentinel_collection.select('NDVI').mean().clip(aos_public_osm_filtered_1ha)
    
    # Create a mask for LPUGS (NDVI >= 0.2)
    lpugs_mask = annual_average_ndvi.gte(0.2).rename('LPUGS')
    
    # Function to add NDVI mean to each feature
    def add_ndvi_to_feature(feature):
        ndvi_value = annual_average_ndvi.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=feature.geometry(),
            scale=10
        ).get('NDVI')
        return feature.set({'NDVI_mean': ndvi_value})

    # Function to calculate LPUGS area in hectares
    def calculate_ndvi_area(feature):
        ndvi_area = lpugs_mask.multiply(ee.Image.pixelArea()).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=feature.geometry(),
            scale=10
        ).get('LPUGS')
        return feature.set({'NDVI_ha': ee.Number(ndvi_area).divide(1e4)})

    # Apply NDVI and area calculations to filtered AOS features
    lpugs_fc = aos_public_osm_filtered_1ha.map(add_ndvi_to_feature).map(calculate_ndvi_area)
    lpugs_filtered = lpugs_fc.filter(ee.Filter.gte('NDVI_mean', 0.2))
    
    # Convert Earth Engine FeatureCollection to GeoDataFrame
    lpugs_gdf = geemap.ee_to_gdf(lpugs_filtered)
    
    # Ensure the geometry column is in the correct format (WKT or WKB)
    lpugs_gdf['geom'] = lpugs_gdf['geometry'].apply(lambda x: x.wkt)  # Convert geometry to WKT
    
    # Define SQL queries for LPUGS table setup
    lpugs_setup_queries = [
        """
        -- Drop the LPUGS table if it exists
        DROP TABLE IF EXISTS large_public_urban_green_space;
        """,
        """
        -- Create the LPUGS table
        CREATE TABLE large_public_urban_green_space (
            lpugs_id SERIAL PRIMARY KEY,
            aos_id INTEGER,
            aos_ha_public FLOAT,
            NDVI_mean FLOAT,
            NDVI_ha FLOAT,
            geom GEOMETRY(Geometry, 4326)
        );
        """,
    ]

    # Insert data into the LPUGS table
    insert_data_sql = """
    INSERT INTO large_public_urban_green_space (aos_id, aos_ha_public, NDVI_mean, NDVI_ha, geom)
    VALUES (:aos_id, :aos_ha_public, :NDVI_mean, :NDVI_ha, ST_SetSRID(ST_GeomFromText(:geom), 4326));
    """

    # Execute the queries
    with r.engine.begin() as connection:
        # Run setup queries
        for sql in lpugs_setup_queries:
            connection.execute(text(sql))
        
        # Insert data row by row
        for _, row in lpugs_gdf.iterrows():
            connection.execute(
                text(insert_data_sql),
                {
                    'aos_id': row['aos_id'],
                    'aos_ha_public': row['aos_ha_public'],
                    'NDVI_mean': row['NDVI_mean'],
                    'NDVI_ha': row['NDVI_ha'],
                    'geom': row['geom']
                }
            )
    

def lpugs_setup_queries(r, ghsci):
    """Create the lpugs_nodes_30m_line table as a subset of aos_public_any_nodes_30m_line."""
    if 'lpugs_nodes_30m_line' in r.tables:
        print(
            'Large Public Urban Green Space (LPUGS) for urban liveability indicators has previously been prepared for this region.\n',
        )
    else:
        lpugs_setup_queries = [
                """
    -- Drop the lpugs_nodes_30m_line table if it exists
    DROP TABLE IF EXISTS lpugs_public_nodes_30m_line;
    """,
                """
    -- Create the lpugs_nodes_30m_line table as a subset of aos_public_any_nodes_30m_line
    -- Only include rows where aos_id exists in large_public_urban_green_space
    CREATE TABLE lpugs_nodes_30m_line AS
    SELECT DISTINCT n.*, l.lpugs_id
    FROM aos_public_any_nodes_30m_line n
    JOIN large_public_urban_green_space l ON n.aos_id = l.aos_id;
    """,
                """
    -- Create an index on the geometry column
    CREATE INDEX lpugs_nodes_30m_line_gix ON lpugs_nodes_30m_line USING GIST (geom);
    """,
        ]
        for sql in lpugs_setup_queries:
            query_start = time.time()
            print(f'\nExecuting: {sql}')
            with r.engine.begin() as connection:
                connection.execute(text(sql))
            print(f'Executed in {(time.time() - query_start) / 60:04.2f} mins')
            


def large_public_urban_green_space(codename):
    # simple timer for log file
    start = time.time()
    script = '_07_large_public_urban_green_space'
    task = 'Prepare Large Public Urban Green Spaces (LPUGS)'
    r = ghsci.Region(codename)
    # Generate and upload LPUGS data
    generate_and_upload_lpugs(codename, r)
    lpugs_setup_queries(r, ghsci)
    # output to completion log
    script_running_log(r.config, script, task, start)
    r.engine.dispose()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    large_public_urban_green_space(codename)


if __name__ == '__main__':
    main()