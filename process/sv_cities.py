"""
now it just works on specific city, should revise in the future
"""
import geopandas as gpd
import pandas as pd
import os
import time
import sv_config as sc


def aggregation(input_gdf, out_gdf, fieldNames):
    """create aggregation result for city from hexes
    Arguments:
        input_gdf {geodataframe} -- [hex]
        out_gdf {geodataframe} -- [city]
        fieldNames {list} -- [zipped input and output fieldnames]
    """
    for field in fieldNames:
        out_gdf[field[1]] = (input_gdf['pop_est'] * input_gdf[field[0]]
                             ).sum() / (input_gdf['pop_est'].sum())
    return out_gdf


startTime = time.time()
dirname = os.path.dirname(__file__)
gpkg_input = os.path.join(dirname, sc.output_hex_250m)
# !!change here layer name
gdf_hex = gpd.read_file(gpkg_input, layer="hex_temp")
# !!change here geopackage
gpkg_origin_hex = os.path.join(dirname, sc.geopackagePath)
gdf_hex_origin = gpd.read_file(gpkg_origin_hex, layer=sc.hex250)
gdf_study_region = gpd.read_file(gpkg_origin_hex, layer=sc.urban_study_region)
# join pop_est from original hex to processed hex
gdf_hex = gdf_hex.join(gdf_hex_origin.set_index('index'),
                       on='index',
                       how='left',
                       rsuffix='_origin')
# or
# gdf_hex=pd.merge(gdf_hex,gdf_hex_origin,on='index',how='left',suffixes=('','_origin'))

gdf_study_region['urban_sample_point_count'] = gdf_hex[
    'urban_sample_point_count'].sum()

fieldNames = [
    'pct_access_500m_supermarkets', 'pct_access_500m_convenience',
    'pct_access_500m_pt_any', 'pct_access_500m_public_open_space',
    'local_nh_population_density', 'local_nh_intersection_density',
    'local_daily_living', 'local_walkability'
]

fieldNames_new = [
    'pop_pct_access_500m_supermarkets', 'pop_pct_access_500m_convenience',
    'pop_pct_access_500m_pt_any', 'pop_pct_access_500m_public_open_space',
    'pop_nh_pop_density', 'pop_nh_intersection_density', 'pop_daily_living',
    'pop_walkability'
]

gdf_study_region = aggregation(gdf_hex, gdf_study_region,
                               list(zip(fieldNames, fieldNames_new)))
gpkg_cities = os.path.join(dirname, sc.output_cities)
# !!change here
gdf_study_region.to_file(gpkg_cities, layer='odense_sample', driver='GPKG')