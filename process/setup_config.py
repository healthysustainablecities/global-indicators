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
import pandas
import time
import sys
import yaml

# Load project configuration
with open('/home/jovyan/work/process/configuration/config.yml') as f:
     config = yaml.safe_load(f)

for group in config.keys():
  for var in config[group].keys():
    globals()[var]=config[group][var]

# Load study region configuration
# the first record is a description, unless modified by user 
with open('/home/jovyan/work/process/configuration/regions.yml') as f:
    regions = yaml.safe_load(f)
    # quietly remove the region description key
    region_description = regions.pop('description',None)

# Load OpenStreetMap destination and open space parameters
df_osm_dest = pandas.read_csv(osm_destination_definitions)

# Load definitions of measures and indicators
with open('/home/jovyan/work/process/configuration/indicators.yml') as f:
     indicators = yaml.safe_load(f)

# parse input city arguments
if len(sys.argv) > 1:
    input_cities = sys.argv[1:]
    input_cities = [x for x in regions.keys() if x in input_cities]
else:
    input_cities = list(regions.keys())

date = time.strftime("%Y-%m-%d")

population_grid = f'population_{hex_diag}{units}_{population["year_target"]}'
gpkg_output_hex = f'{output_folder}/global_indicators_hex_{hex_diag}{units}_{date}.gpkg'
gpkg_output_cities = f'{output_folder}/global_indicators_city_{date}.gpkg'

neighbourhood_variables = ['index', 'study_region', 'area_sqkm', 'pop_est', 'pop_per_sqkm', 'intersection_count', 'intersections_per_sqkm', 'urban_sample_point_count', 'pct_access_500m_fresh_food_market_score', 'pct_access_500m_convenience_score', 'pct_access_500m_pt_osm_any_score', 'pct_access_500m_public_open_space_any_score', 'pct_access_500m_public_open_space_large_score', 'pct_access_500m_pt_gtfs_any_score', 'pct_access_500m_pt_gtfs_freq_30_score', 'pct_access_500m_pt_gtfs_freq_20_score', 'pct_access_500m_pt_any_score', 'local_nh_population_density', 'local_nh_intersection_density', 'local_daily_living', 'local_walkability', 'geometry']

city_variables = ['study_region', 'area_sqkm', 'pop_est', 'pop_per_sqkm', 'intersection_count', 'intersections_per_sqkm', 'urban_sample_point_count', 'pop_pct_access_500m_fresh_food_market_score', 'pop_pct_access_500m_convenience_score', 'pop_pct_access_500m_pt_osm_any_score', 'pop_pct_access_500m_public_open_space_any_score', 'pop_pct_access_500m_public_open_space_large_score', 'pop_pct_access_500m_pt_gtfs_any_score', 'pop_pct_access_500m_pt_gtfs_freq_30_score', 'pop_pct_access_500m_pt_gtfs_freq_20_score', 'pop_pct_access_500m_pt_any_score', 'pop_nh_pop_density', 'pop_nh_intersection_density', 'pop_daily_living', 'pop_walkability', 'geometry']

for city in regions.keys()
    study_region = f"{city}_{region}_{year}"
    regions[city]['study_region'] = study_region
    regions[city]['data'] = {}
    regions[city]['data']['gpkg'] =
    if regions[city]['network_not_using_buffered_region']:
        regions['city']['data']['graphml'] = f"{study_region}_pedestrian_osm_{osm_date}.graphml"
    else:
        regions['city']['data']['graphml'] = f"{study_region}_{study_buffer}m_pedestrian_osm_{osm_date}.graphml"
if __name__ == "__main__":
    # Generate study region configuration files
    for i in range(len(cities)):
        # generate dict of study region input datasource parameters
        city = cities[i]["cityname"]
        region = cities[i]["region"]
        to_crs = cities[i]["crs"]
        city_folder = f'study_region/{city}_{region}_{year}'
        gpkg = f"{city_folder}/{city}_{region}_{year}_{study_buffer}m_buffer.gpkg"
        gpkg_out = f"output/{city}_{region}_{year}_{study_buffer}m_buffer_output{output_date}.gpkg"
        if 'no_graphml_buffer' in cities[i] and cities[i]['no_graphml_buffer']:
            # a city can be parameterised to not buffer graphml in exceptional circumstances --- e.g. Hong Kong
            graphmlName = f"{city}_{region}_{year}_pedestrian_osm_{osm_date}.graphml"
            graphmlProj_name = f"{city}_{region}_{year}_pedestrian_osm_{osm_date}_proj.graphml"
        else:
            graphmlName = f"{city}_{region}_{year}_{study_buffer}m_pedestrian_osm_{osm_date}.graphml"
            graphmlProj_name = f"{city}_{region}_{year}_{study_buffer}m_pedestrian_osm_{osm_date}_proj.graphml"
        city_config = f"""# Global Indicators project

# Generated configuration file for {city.title()}
# {time.strftime("%Y-%m-%d")}

config={{
        "study_region": "{city}",
        "study_region_full": "{city}_{region}_{year}",
        "region":"{region}",
        "year":"{year}",
        "to_crs": "{to_crs}",
        "geopackagePath": '{gpkg}',
        "geopackagePath_output": '{gpkg_out}',
        "graphmlName": '{city_folder}/{graphmlName}',
        "graphmlProj_name": '{city_folder}/{graphmlProj_name}',
        "folder": "data",
        "nodes_pop_intersect_density": "output/nodes_pop_intersect_density_{city}.csv",

parameters={{
    "samplePointsData_withoutNan": "samplePointsData_withoutNan",
    "samplePoints": "urban_sample_points",
    "destinations": "destinations",
    "fresh_food_market": "Fresh Food / Market",
    "convenience": "Convenience",
    "pt_any": "Public transport stop (any)",
    "pt_stops_headway": "Public transport stop (gtfs)",
    "population_grid": f'population_{hex_diag}{units}_{population["year_target"]}',
    "pos": "aos_public_any_nodes_30m_line",
    "nodes": "nodes",
    "edges": "edges",
    "accessibility_distance": {accessibility_distance},
    "neighbourhood_distance": {neighbourhood_distance},
    "dropNan": "samplePointsData_droped_nan",
    "tempLayer": "samplePointsData_pop_intersect_density",
    "samplepointResult": samplepointResult,
    "population_density":"sp_local_nh_avg_pop_density",
    "intersection_density":"sp_local_nh_avg_intersection_density",
    "pop_min_threshold": {pop_min_threshold}
}}"""

