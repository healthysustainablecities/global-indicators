################################################################################
# Script: setup_config.py
# Description: This script defines project parameters and prepare configuration file for all study regions
# All the cities should run this script first to create configuration file in json
# before running the sample point and aggregation scripts.

# Two major outputs:
# 1. study region configuration json (e.g. odense.json; phoenix.json)
# 2. cities.json

################################################################################
import json
import os
import sys
import time

# define project parameters
# list of cities that are needed to be set up
cities = ['adelaide', 'auckland', 'baltimore', 'bangkok', 'barcelona', 'belfast', 'bern', 'chennai',
          'cologne', 'ghent', 'graz', 'hanoi', 'hong_kong', 'lisbon', 'melbourne', 'mexico_city',
          'odense', 'olomouc', 'phoenix', 'sao_paulo', 'seattle', 'sydney', 'valencia', 'vic']

# list of countries regions, follow the order of list of cities above
regions = ['au', 'nz', 'us', 'th', 'es', 'gb', 'ch', 'in',
           'de', 'be', 'at', 'vn', 'hk', 'pt', 'au', 'mx',
           'dk', 'cz', 'us', 'br', 'us', 'au', 'es', 'es']

# list of UTM zone, follow the order of list of cities above
to_crs = [7845, 2193, 32618, 32647, 25831, 29902, 32633, 32644,
          32631, 32631, 32633, 32648, 32650, 3763, 7845, 32614,
          32632, 32633, 32612, 32723, 32610, 7845, 25830, 25831]

project_year = 2019 # Year that the current indicators are targetting
osm_input_date = 20190902 # Date at which OSM download was current
output_date = 20200402 # Date at which the output date were generated
study_buffer = 10000 # Study region buffer, to account for edge effects, in meters
distance = 1600 # sausage buffer network size, in meters

# study region data parameters
# these are parameters in study region input gpkg
parameters = {
        "samplePointsData_withoutNan": "samplePointsData_withoutNan",
        "samplePoints": "urban_sample_points",
        "destinations": "destinations",
        "supermarket": "Fresh Food / Market",
        "convenience": "Convenience",
        "PT": "Public transport stop (any)",
        "hex250": "pop_ghs_2015",
        "urban_study_region": "urban_study_region",
        "pos": "aos_nodes_30m_line",
        "nodes": "nodes",
        "edges": "edges",
        "accessibility_distance": 500,
        "search_distance": 1600,
        "dropNan": "samplePointsData_droped_nan",
        "tempLayer": "samplePointsData_pop_intersect_density",
        "samplepointResult": "samplePointsData"}

# specify study region sample point stats field name
# these are sample point variables in "samplePointsData_withoutNan" layer within study region input gpkg
samplePoint_fieldNames = {
        "sp_local_nh_avg_pop_density": "sp_local_nh_avg_pop_density",
        "sp_local_nh_avg_intersection_density": "sp_local_nh_avg_intersection_density",
        "sp_nearest_node_supermarket_dist": "sp_nearest_node_supermarket_dist",
        "sp_nearest_node_supermarket_binary": "sp_nearest_node_supermarket_binary",
        "sp_nearest_node_convenience_dist": "sp_nearest_node_convenience_dist",
        "sp_nearest_node_convenience_binary": "sp_nearest_node_convenience_binary",
        "sp_nearest_node_pt_dist": "sp_nearest_node_pt_dist",
        "sp_nearest_node_pt_binary": "sp_nearest_node_pt_binary",
        "sp_nearest_node_pos_dist": "sp_nearest_node_pos_dist",
        "sp_nearest_node_pos_binary": "sp_nearest_node_pos_binary",
        "sp_daily_living_score": "sp_daily_living_score",
        "sp_zscore_local_nh_avgpopdensity": "sp_zscore_local_nh_avgpopdensity",
        "sp_zscore_local_nh_avgintdensity": "sp_zscore_local_nh_avgintdensity",
        "sp_zscore_daily_living_score": "sp_zscore_daily_living_score",
        "sp_walkability_index": "sp_walkability_index"
    }

# cities aggregation data parameters
# these are parameters for all cities needed to generated output gpkg
cities_parameters = {
    "folder" : "data/output",
    "input_folder" : "data/input",
    "samplepointResult": "samplePointsData",
    "hex250": "pop_ghs_2015",
    "urban_study_region": "urban_study_region",
    "pop_est": "pop_est",
    "output_hex_250m": "global_indicators_hex_250m.gpkg",
    "global_indicators_city": "global_indicators_city.gpkg"}

# specify study region hex-level output indicators field name
# these are within-city varaibles names in global_indicators_hex_250m.gpkg
hex_fieldNames = {
    "index": "index",
    "study_region": "study_region",
    "urban_sample_point_count": "urban_sample_point_count",
    "pct_access_500m_supermarkets": "pct_access_500m_supermarkets",
    "pct_access_500m_convenience": "pct_access_500m_convenience",
    "pct_access_500m_pt_any": "pct_access_500m_pt_any",
    "pct_access_500m_public_open_space": "pct_access_500m_public_open_space",
    "local_nh_population_density": "local_nh_population_density",
    "local_nh_intersection_density": "local_nh_intersection_density",
    "local_daily_living": "local_daily_living",
    "local_walkability": "local_walkability",
    "all_cities_z_nh_population_density": "all_cities_z_nh_population_density",
    "all_cities_z_nh_intersection_density": "all_cities_z_nh_intersection_density",
    "all_cities_z_daily_living": "all_cities_z_daily_living",
    "all_cities_walkability": "all_cities_walkability",
    "geometry": "geometry"}

# specify between cities city-level output indicators field name
# these are between-city varaibles names in global_indicators_city.gpkg

city_fieldNames = {
    "study_region": "study_region",
    "urban_sample_point_count": "urban_sample_point_count",
    "pop_pct_access_500m_supermarkets": "pop_pct_access_500m_supermarkets",
    "pop_pct_access_500m_convenience": "pop_pct_access_500m_convenience",
    "pop_pct_access_500m_pt_any": "pop_pct_access_500m_pt_any",
    "pop_pct_access_500m_public_open_space": "pop_pct_access_500m_public_open_space",
    "pop_nh_pop_density": "pop_nh_pop_density",
    "pop_nh_intersection_density": "pop_nh_intersection_density",
    "pop_daily_living": "pop_daily_living",
    "pop_walkability": "pop_walkability",
    "all_cities_pop_z_nh_population_density": "all_cities_pop_z_nh_population_density",
    "all_cities_pop_z_nh_intersection_density": "all_cities_pop_z_nh_intersection_density",
    "all_cities_pop_z_daily_living": "all_cities_pop_z_daily_living",
    "all_cities_walkability": "all_cities_walkability",
    "geometry": "geometry"}



if __name__ == '__main__':
    # prepare city specific configuration json file
    print("Generate study region configuration json file")
    startTime = time.time()

    for city, region, to_crs in zip(cities, regions, to_crs):
        # generate dict of study region input datasource parameters
        city_config = {
        "study_region": "{city}".format(city=city),
        "to_crs": {"init": "epsg:{crs}".format(crs=to_crs)},
        "geopackagePath": "{city}_{region}_{project_year}_{distance}m_buffer.gpkg".format(
                city=city, region=region, project_year=project_year, distance=distance),
        "geopackagePath_output": "{city}_{region}_{project_year}_{distance}m_buffer_output{output_date}.gpkg".format(
                city=city, region=region, project_year=project_year, distance=distance, output_date=output_date),
        "graphmlName": "{city}_{region}_{project_year}_{study_buffer}m_pedestrian_osm_{osm_input_date}.graphml".format(
                city=city, region=region, project_year=project_year, study_buffer=study_buffer, osm_input_date=osm_input_date),
        "graphmlProj_name": "{city}_{region}_{project_year}_{study_buffer}m_pedestrian_osm_{osm_input_date}_proj.graphml".format(
                city=city, region=region, project_year=project_year, study_buffer=study_buffer, osm_input_date=osm_input_date),
        "folder": "data/input",
        "tempCSV" : "nodes_pop_intersect_density_{city}.csv".format(city=city)
        }
        # serializing json, write to file
        with open("configuration/{city}.json".format(city=city), "w") as write_file:
            json.dump(city_config, write_file, indent=4)



    # prepare cities configuration json file for aggregation
    print("Generate cities aggregation configuration json file")

    gpkgNames = {}
    cities_config = {}

    for city, region in zip(cities, regions):
        gpkgName = {"{city}".format(city=city): "{city}_{region}_{project_year}_{distance}m_buffer_output{output_date}.gpkg".format(
                city=city, region=region, project_year=project_year, distance=distance, output_date=output_date)}
        gpkgNames.update(gpkgName)

    cities_config = {"gpkgNames" : gpkgNames}
    cities_config.update(cities_parameters)
    cities_config.update({"hex_fieldNames" : hex_fieldNames})
    cities_config.update({"city_fieldNames" : city_fieldNames})

    with open("configuration/cities.json", "w") as write_file:
            json.dump(cities_config, write_file, indent=4)
    
    endTime = time.time() - startTime
    print('All study region configuration file were generated, total time is : {0:.2f} hours or {1:.2f} seconds'.format(
        endTime / 3600, endTime))