"""
Initialize Google Earth Engine connection and identify large public urban green space (LPUGS)

"""

# Import project configuration file
import ghsci
import psycopg2

import os
import sys
import json
import ee
import geemap

import geopandas as gpd
from sqlalchemy import create_engine

# INITIALIZE GOOGLE EARTH ENGINE PROJECT

ee.Initialize(project = 'ee-global-indicators')

# Function to fetch urban study region and aos_public_osm as GeoJSON
def fetch_data_as_geojson(codename):
    r = ghsci.Region(codename)
    db_host = r.config['db_host']
    db_port = r.config['db_port']
    db_user = r.config['db_user']
    db_pwd = r.config['db_pwd']
    db = r.config['db']

    # Create a connection string and engine using SQLAlchemy
    connection_string = f"postgresql://{db_user}:{db_pwd}@{db_host}:{db_port}/{db}"
    engine = create_engine(connection_string)

    # Query to fetch urban study region and ensure it's in WGS84 (EPSG:4326)
    urban_study_region_query = """
        SELECT ST_Transform(geom, 4326) AS geom
        FROM urban_study_region;
    """
    urban_study_region_gdf = gpd.read_postgis(urban_study_region_query, con=engine, geom_col='geom')

    # Query to fetch aos_public_osm and ensure it's in WGS84 (EPSG:4326)
    aos_public_osm_query = """
        SELECT ST_Transform(geom, 4326) AS geom, aos_public_osm.aos_ha_public
        FROM aos_public_osm;
    """
    aos_public_osm_gdf = gpd.read_postgis(aos_public_osm_query, con=engine, geom_col='geom')

    # Convert both to GeoJSON format
    urban_study_region_geojson = urban_study_region_gdf.to_json()
    aos_public_osm_geojson = aos_public_osm_gdf.to_json()

    engine.dispose()  # Close the database connection

    return urban_study_region_geojson, aos_public_osm_geojson

def main():
    codename = sys.argv[1]
    urban_study_region_geojson, aos_public_osm_geojson = fetch_data_as_geojson(codename)

    # Load the GeoJSON into Earth Engine
    urban_study_region_fc = ee.FeatureCollection(json.loads(urban_study_region_geojson))
    aos_public_osm_fc = ee.FeatureCollection(json.loads(aos_public_osm_geojson))

    # Export the FeatureCollection as GeoJSON
    out_dir = os.path.expanduser("/home/ghsci")
    out_shp = os.path.join(out_dir, "urban_study_region_fc_TEST.shp")
    geemap.ee_to_shp(urban_study_region_fc, out_shp)

    out_shp = os.path.join(out_dir, "aos_public_osm_fc_TEST.shp")
    geemap.ee_to_shp(aos_public_osm_fc, out_shp)

    print('Number of AOS Public OSM in FeatureCollection:', aos_public_osm_fc.size().getInfo())

    # Filter for area greater than or equal to 1 ha
    aos_public_osm_filtered_1ha = aos_public_osm_fc.filter(ee.Filter.gte('aos_ha_public', 1))

    out_shp = os.path.join(out_dir, "aos_public_osm_filtered_1ha_reprojected_TEST.shp")
    geemap.ee_to_shp(aos_public_osm_filtered_1ha, out_shp)
    
    # Define analysis dates as the year from March 1st 2023 to March 1st 2024
    start_date = '2023-03-01'
    end_date = '2024-03-01'

    # # Define map
    # Map = geemap.Map()

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
    attribute_name_ndvi_aa = 'NDVI_aa_av'
    attribute_name_lpugs_area_aa = 'LPUGS_aa_ha'
    with_annual_average_ndvi = aos_public_osm_filtered_1ha.map(lambda feature: add_ndvi_to_feature(feature, annual_average_ndvi_image_clipped, name=attribute_name_ndvi_aa))
    aos_public_osm_lpugs = with_annual_average_ndvi.map(lambda feature: calculate_ndvi_area(feature, lpugs_areas_annual_average_clip, name=attribute_name_lpugs_area_aa))

    # Filter for NDVI greater than or equal to 0.2
    aos_public_osm_lpugs_ndvi_0point2 = aos_public_osm_lpugs.filter(ee.Filter.gte('NDVI_aa_av', 0.2))

    out_shp = os.path.join(out_dir, "aos_public_osm_lpugs_ndvi_0point2.shp")
    geemap.ee_to_shp(aos_public_osm_lpugs_ndvi_0point2, out_shp)

if __name__ == '__main__':
    main()