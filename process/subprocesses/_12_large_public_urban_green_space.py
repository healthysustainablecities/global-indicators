"""
Identify large public urban green space (LPUGS) through use of the Google Earth Engine API
"""
import os
import sys
import time
import json
import calendar
from datetime import datetime, timedelta

# Import Earth Engine and Google Earth Engine Map libraries
import ee
import geemap
import psycopg2
import geopandas as gpd

# import getpass
from script_running_log import script_running_log
from sqlalchemy import create_engine

import ghsci


# Function to connect to the database
def connect_to_database(r):
    """Establish connection to the PostgreSQL database using SQLAlchemy."""
    db_host = r.config['db_host']
    db_port = r.config['db_port']
    db_user = r.config['db_user']
    db_pwd = r.config['db_pwd']
    db = r.config['db']
    
    try:
        engine = create_engine(f'postgresql://{db_user}:{db_pwd}@{db_host}:{db_port}/{db}')
        print(f"Successfully connected to the database: {db}")
        return engine
    except Exception as e:
        print(f"Failed to connect to the database: {e}")
        sys.exit(1)

 
# Function to fetch urban study region and aos_public_osm as GeoJSON
def fetch_data_as_geojson(codename):
    r = ghsci.Region(codename)
    engine = connect_to_database(r)

    # Fetch data using GeoPandas
    urban_study_region_query = """
        SELECT ST_Transform(geom, 4326) AS geom
        FROM urban_study_region;
    """
    urban_study_region_gdf = gpd.read_postgis(urban_study_region_query, con=engine, geom_col='geom')

    aos_public_osm_query = """
        SELECT ST_Transform(geom, 4326) AS geom, aos_public_osm.aos_ha_public
        FROM aos_public_osm;
    """
    aos_public_osm_gdf = gpd.read_postgis(aos_public_osm_query, con=engine, geom_col='geom')
    
    network_query = """
        SELECT geom
        FROM edges;
    """
    network_gdf = gpd.read_postgis(network_query, con=engine, geom_col='geom')
    
    urban_sample_points_query = """
        SELECT geom
        FROM urban_sample_points;
    """
    urban_sample_points_gdf = gpd.read_postgis(urban_sample_points_query, con=engine, geom_col='geom')
    
    population_grid_query = """
    SELECT geom
    FROM population_100m_2020;
    """
    population_grid_gdf = gpd.read_postgis(population_grid_query, con=engine, geom_col='geom')

    # Convert to GeoJSON
    urban_study_region_geojson = urban_study_region_gdf.to_json()
    aos_public_osm_geojson = aos_public_osm_gdf.to_json()
    network_geojson = network_gdf.to_json()
    urban_sample_points_geojson = urban_sample_points_gdf.to_json()
    population_grid_geojson = population_grid_gdf.to_json()

    return urban_study_region_geojson, aos_public_osm_geojson, network_geojson, urban_sample_points_geojson, population_grid_geojson


def generate_lpugs(codename, r):
    # Fetch urban study region and aos_public_osm    
    urban_study_region_geojson, aos_public_osm_geojson, network_geojson, urban_sample_points_geojson, population_grid_geojson = fetch_data_as_geojson(codename)
    
    # Initialize Google Earth Engine API connection
    project_id = r.config['gee_project_id']
    ee.Initialize(project = project_id)

    # Load the GeoJSON into Earth Engine
    urban_study_region_fc = ee.FeatureCollection(json.loads(urban_study_region_geojson))
    aos_public_osm_fc = ee.FeatureCollection(json.loads(aos_public_osm_geojson))
    
    # Filter for area greater than or equal to 1 ha
    aos_public_osm_filtered_1ha = aos_public_osm_fc.filter(ee.Filter.gte('aos_ha_public', 1))
    
    # Fetch the target year specified in user config file
    target_year = r.config['year']
    
    # Create start and end dates dynamically and convert to string format 'YYYY-MM-DD'
    start_date = (datetime(target_year, 1, 1)).strftime('%Y-%m-%d')  # Start date: 1st January of target_year
    end_date = (datetime(target_year + 1, 1, 1)).strftime('%Y-%m-%d')  # End date: 1st January of the following year

    city = urban_study_region_fc

    # Get the geometry and bounding box
    geometry = city.geometry()
    bounding_box = geometry.bounds()
        
    # SENTINEL MASK CLOUDS AND NDVI FUNCTION

    # Function to mask clouds from Sentinel 2 imagery using the QA band
    def mask_s2_clouds(image):
        qa = image.select('QA60')
        
        # Bits 10 and 11 are clouds and cirrus, respectively
        cloud_bit_mask = 1 << 10
        cirrus_bit_mask = 1 << 11
        
        # Both flags should be set to zero, indicating clear conditions
        mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
        
        # Return the masked and scaled data, without the QA bands
        return image.updateMask(mask).divide(10000).select(["B.*"]).copyProperties(image, ["system:time_start"])

    # Calculate NDVI
    def calculate_ndvi(image):
        nir = image.select('B8')  # Near-infrared band
        red = image.select('B4')  # Red band
        ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI')
        return image.addBands(ndvi)

    # NDVI CALCULATION - ANNUAL AVERAGE - SENTINEL

    # Load Sentinel-2 TOA reflectance data using dates for the whole year of 2020 defined at the start of this notebook
    sentinel_collection_annual_average = ee.ImageCollection('COPERNICUS/S2_HARMONIZED') \
        .filterBounds(bounding_box) \
        .filterDate(start_date, end_date) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 90)) \
        .map(mask_s2_clouds)

    # Apply NDVI calculation to the image collection
    annual_average_ndvi_collection = sentinel_collection_annual_average.map(calculate_ndvi)

    # Calculate the overall average NDVI for all 12 months of the year
    annual_average_ndvi = annual_average_ndvi_collection.select('NDVI').mean()

    # Clip the NDVI image to the areas of open space to save processing time
    annual_average_ndvi_image_clipped = annual_average_ndvi.clip(aos_public_osm_filtered_1ha)

    # Clip the NDVI image to the city boundary
    annual_average_ndvi_image_clipped_city = annual_average_ndvi.clip(city)

    # Create a binary mask greater than or equal to NDVI 0.2
    binary_ndvi = annual_average_ndvi_image_clipped_city.gte(0.2).rename('Binary_NDVI')

    # DEFINE PUBLIC URBAN GREEN SPACE

    # LPUGS defined as NDVI 0.2 - 1
    min_NDVI = 0.2
    max_NDVI = 1

    # Define mask based on max and min NDVI thresholds for annual average

    lpugs_areas_annual_average = annual_average_ndvi_image_clipped.gte(min_NDVI).And(annual_average_ndvi_image_clipped.lte(max_NDVI))

    # Apply mask
    lpugs_areas_annual_average_clip = lpugs_areas_annual_average.updateMask(
        lpugs_areas_annual_average.gte(min_NDVI).And(lpugs_areas_annual_average.lte(max_NDVI))
    )

    # ADD NDVI ATTRIBUTES TO EACH AOS_PUBLIC_OSM

    def add_ndvi_to_feature(feature, image, name='NDVI'):
        # Get the geometry of the feature
        geometry = feature.geometry()

        # Use reduceRegion to calculate the mean NDVI value within each polygon
        ndvi_value = image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=10
        ).get('NDVI')

        # Set the calculated rounded NDVI as a property of the feature
        return feature.set({name: ndvi_value})

    def calculate_ndvi_area(feature, image, name='LPUGS_area'):   
        geometry = feature.geometry()
        ndvi_area = image.multiply(ee.Image.pixelArea()).rename('Area')
        ndvi_area_calc = ndvi_area.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geometry,
            scale=10,
            maxPixels=1e10
        )
        ndvi_area_m2 = ee.Number(ndvi_area_calc.get('Area'))
        ndvi_area_ha = ndvi_area_m2.divide(1e4)
        
        # Set the calculated LPUGS area as a property of the feature
        return feature.set({name: ndvi_area_ha})

    # Usage example
    attribute_name_ndvi_mean = 'NDVI_mean'
    attribute_name_lpugs_area = 'LPUGS_ha'
    with_annual_average_ndvi = aos_public_osm_filtered_1ha.map(lambda feature: add_ndvi_to_feature(feature, annual_average_ndvi_image_clipped, name=attribute_name_ndvi_mean))
    aos_public_osm_lpugs = with_annual_average_ndvi.map(lambda feature: calculate_ndvi_area(feature, lpugs_areas_annual_average_clip, name=attribute_name_lpugs_area))

    # Filter for NDVI greater than or equal to 0.2
    aos_public_osm_lpugs_ndvi_0point2 = aos_public_osm_lpugs.filter(ee.Filter.gte('NDVI_mean', 0.2))
    
    # Export the FeatureCollection as GeoJSON
    out_dir = os.path.expanduser("/home/ghsci")
    out_shp = os.path.join(out_dir, "aos_public_osm_lpugs_ndvi_0point2.shp")
    geemap.ee_to_shp(aos_public_osm_lpugs_ndvi_0point2, out_shp)


def large_public_urban_green_space(codename):
    # simple timer for log file
    start = time.time()
    script = '_12_large_public_urban_green_space'
    task = 'Prepare Large Public Urban Green Spaces (LPUGS)'
    r = ghsci.Region(codename)
    generate_lpugs(codename, r)
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