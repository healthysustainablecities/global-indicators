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
import time
import sys

# define project parameters
project_year = 2019  # Year that the current indicators are targetting
osm_input_date = 20200813  # Date at which OSM download was current
gtfs_analysis_date = 20200827 # Date on which the GTFS data were analysed and output; yyyy-mm-dd string
output_date = 20200901  # Date at which the output data are getting prepared
study_buffer = 1600  # Study region buffer, to account for edge effects, in meters
neighbourhood_distance = 1600  # sausage buffer network size, in meters
accessibility_distance = 500

# list of cities that are needed to be set up (filtered based on input city command line arguments
cities = [
    {"cityname": "adelaide", "region": "au", "crs": "epsg:7845"},
    {"cityname": "auckland", "region": "nz", "crs": "epsg:2193"},
    {"cityname": "baltimore", "region": "us", "crs": "epsg:32618"},
    {"cityname": "bangkok", "region": "th", "crs": "epsg:32647"},
    {"cityname": "barcelona", "region": "es", "crs": "epsg:25831"},
    {"cityname": "belfast", "region": "gb", "crs": "epsg:29902"},
    {"cityname": "bern", "region": "ch", "crs": "epsg:32633"},
    {"cityname": "chennai", "region": "in", "crs": "epsg:32644"},
    {"cityname": "cologne", "region": "de", "crs": "epsg:32631"},
    {"cityname": "ghent", "region": "be", "crs": "epsg:32631"},
    {"cityname": "graz", "region": "at", "crs": "epsg:32633"},
    {"cityname": "hanoi", "region": "vn", "crs": "epsg:32648"},
    {"cityname": "hong_kong", "region": "hk", "crs": "epsg:32650","no_graphml_buffer":True},
    {"cityname": "lisbon", "region": "pt", "crs": "epsg:3763"},
    {"cityname": "melbourne", "region": "au", "crs": "epsg:7845"},
    {"cityname": "mexico_city", "region": "mx", "crs": "epsg:32614"},
    {"cityname": "odense", "region": "dk", "crs": "epsg:32632"},
    {"cityname": "olomouc", "region": "cz", "crs": "epsg:32633"},
    {"cityname": "phoenix", "region": "us", "crs": "epsg:32612"},
    {"cityname": "sao_paulo", "region": "br", "crs": "epsg:32723"},
    {"cityname": "seattle", "region": "us", "crs": "epsg:32610"},
    {"cityname": "sydney", "region": "au", "crs": "epsg:7845"},
    {"cityname": "valencia", "region": "es", "crs": "epsg:25830"},
    {"cityname": "vic", "region": "es", "crs": "epsg:25831"},
]

if len(sys.argv) > 1:
    input_cities = sys.argv[1:]
    cities = [x for x in cities if x['cityname'] in input_cities]
else:
    input_cities = [x['cityname'] for x in cities]

# read in GTFS config
exec(open('./data/GTFS/gtfs_config.py').read())
# filter GTFS to input city list
for city in [c for c in GTFS.keys() if c not in input_cities]:
    del(GTFS[city])
# format GTFS date to yyyy-mm-dd format string
gtfs_analysis_date = f'{str(gtfs_analysis_date)[0:4]}-{str(gtfs_analysis_date)[4:6]}-{str(gtfs_analysis_date)[6:]}'
gtfs_gpkg = f'./data/GTFS/gtfs_frequent_transit_headway_{gtfs_analysis_date}_python.gpkg'
# add GTFS layer for each city
for city in cities:
    if len(GTFS[city['cityname']])>0:
        cities[cities.index(city)]['gtfs_layer'] = f"{city['cityname']}_stops_headway_{GTFS[city['cityname']][-1]['start_date_mmdd']}_{GTFS[city['cityname']][-1]['end_date_mmdd']}"
    else:
        cities[cities.index(city)]['gtfs_layer'] = None

# study region data parameters
# these are parameters in study region input gpkg
parameters = {
    "samplePointsData_withoutNan": "samplePointsData_withoutNan",
    "samplePoints": "urban_sample_points",
    "destinations": "destinations",
    "fresh_food_market": "Fresh Food / Market",
    "convenience": "Convenience",
    "PT": "Public transport stop (any)", # Note - this is OSM; GTFS and combination measures accuonted for elsewhere
    "hex250": "pop_ghs_2015",
    "urban_study_region": "urban_study_region",
    "pos": "aos_public_any_nodes_30m_line",
    "nodes": "nodes",
    "edges": "edges",
    "accessibility_distance": accessibility_distance,
    "neighbourhood_distance": neighbourhood_distance,
    "dropNan": "samplePointsData_droped_nan",
    "tempLayer": "samplePointsData_pop_intersect_density",
    "samplepointResult": "samplePointsData",
    "population_density":"nh_population_density",
    "intersection_density":"nh_intersection_density"
}

prefixes = {
    'sample_points_final':'sp',
    'sample_point_nodes':'sp_nearest_node',
    'population_access':f'pct_access_{accessibility_distance}m',
    'sample_point_zscores':'sp_zscore'
}

# specify study region sample point stats field name
# these are sample point variables in 'samplePointsData_withoutNan' layer within study region input gpkg
samplePoint_fieldNames = [
    "sp_local_nh_population_density",
    "sp_local_nh_intersection_density",
    "sp_fresh_food_market_dist_m",
    "sp_access_fresh_food_market_binary",
    "sp_convenience_dist_m",
    "sp_access_convenience_binary",
    "sp_pt_dist_m",
    "sp_access_pt_binary",
    "sp_pos_dist_m",
    "sp_access_pos_binary",
    "sp_daily_living_score",
    "sp_zscore_local_nh_avgpopdensity",
    "sp_zscore_local_nh_avgintdensity",
    "sp_zscore_daily_living_score",
    "sp_walkability_index"]

# wrong order --- but if order doesn't matter this could work
# fieldNames_from_samplePoint = [x for x in samplePoint_fieldNames if not sum([o in x for o in ['dist_m','zscore']])]

fieldNames_from_samplePoint = ["sp_access_fresh_food_market_binary", 
                               "sp_access_convenience_binary", 
                               "sp_access_pt_binary", 
                               "sp_access_pos_binary", 
                               "sp_local_nh_population_density", 
                               "sp_local_nh_intersection_density", 
                               "sp_daily_living_score", 
                               "sp_walkability_index"]

fieldNames2hex = ["pct_access_500m_fresh_food_markets", 
                  "pct_access_500m_convenience", 
                  "pct_access_500m_pt_any", 
                  "pct_access_500m_public_open_space", 
                  "local_nh_population_density", 
                  "local_nh_intersection_density", 
                  "local_daily_living", 
                  "local_walkability"]

# cities aggregation data parameters
# these are parameters for all cities needed to generated output gpkg
cities_parameters = {
    "folder": "data/output",
    "input_folder": "data/input",
    "samplepointResult": "samplePointsData",
    "hex250": "pop_ghs_2015",
    "urban_study_region": "urban_study_region",
    "pop_est": "pop_est",
    "output_hex_250m": "global_indicators_hex_250m.gpkg",
    "global_indicators_city": "global_indicators_city.gpkg",
}

# specify study region hex-level output indicators field name
# these are within-city variable names in global_indicators_hex_250m.gpkg
# ?? All identical keys and values --- this data structure may be redundant given code implementation?
hex_fieldNames = ["index",
                  "study_region",
                  "urban_sample_point_count",
                  "pct_access_500m_fresh_food_markets",
                  "pct_access_500m_convenience",
                  "pct_access_500m_pt_any",
                  "pct_access_500m_public_open_space",
                  "local_nh_population_density",
                  "local_nh_intersection_density",
                  "local_daily_living",
                  "local_walkability",
                  "all_cities_z_nh_population_density",
                  "all_cities_z_nh_intersection_density",
                  "all_cities_z_daily_living",
                  "all_cities_walkability",
                  "geometry"]


# specify between cities city-level output indicators field name
# these are between-city varaibles names in global_indicators_city.gpkg
city_fieldNames = [x.replace('local_nh_population','pop_nh_pop') \
                    .replace('pct','pop_pct') \
                    .replace('local','pop') \
                    .replace('_z_','_pop_z_') \
                        for x in hex_fieldNames if x!='index']

if __name__ == "__main__":
    # prepare city specific configuration json file
    print("Generate study region configuration json file")
    startTime = time.time()

    for i in range(len(cities)):
        # generate dict of study region input datasource parameters
        city = cities[i]["cityname"]
        region = cities[i]["region"]
        to_crs = cities[i]["crs"]
        gpkg = f"{city}_{region}_{project_year}_{neighbourhood_distance}m_buffer.gpkg"
        if 'no_graphml_buffer' in cities[i] and cities[i]['no_graphml_buffer']:
            # a city can be parameterised to not buffer graphml in exceptional circumstances --- e.g. Hong Kong
            graphmlName = f"{city}_{region}_{project_year}_pedestrian_osm_{osm_input_date}.graphml"
            graphmlProj_name = f"{city}_{region}_{project_year}_pedestrian_osm_{osm_input_date}_proj.graphml"
        else:
            graphmlName = f"{city}_{region}_{project_year}_{study_buffer}m_pedestrian_osm_{osm_input_date}.graphml"
            graphmlProj_name = f"{city}_{region}_{project_year}_{study_buffer}m_pedestrian_osm_{osm_input_date}_proj.graphml"
        city_config = {
            "study_region": f"{city}",
            "to_crs": f"{to_crs}",
            "geopackagePath": gpkg,
            "geopackagePath_output": f"{city}_{region}_{project_year}_{neighbourhood_distance}m_buffer_output{output_date}.gpkg",
            "graphmlName": graphmlName,
            "graphmlProj_name": graphmlProj_name,
            "folder": "data/input",
            "tempCSV": f"nodes_pop_intersect_density_{city}.csv",
            "nearest_node_analyses":{
                'daily_living':{
                    'geopackage': gpkg,
                    'layers':['destinations'],
                    'category_field':'dest_name',
                    'categories': ['fresh_food_market','convenience','pt_osm_any'],
                    'filter_field': None,
                    'filter_iterations': None,
                    'output_names': ['fresh_food_market','convenience','pt_osm_any'], 
                    'notes': "The initial value for pt_any will be based on analysis using OSM data; this will later be copied to a seperate pt_any_osm result, and the final pt_any variable will be based on the 'best result' out of analysis using GTFS data (where available) and OSM data"   
                },
                'open_space':{
                    'geopackage': gpkg,
                    'layers':['aos_public_any_nodes_30m_line','aos_public_large_nodes_30m_line'],
                    'category_field':None,
                    'categories': [],
                    'filter_field': None,
                    'filter_iterations': None,
                    'output_names':["public_open_space_any","public_open_space_large"],
                    'notes':None
                },
                'public_transport':{
                    'geopackage': gtfs_gpkg,
                    'layers':cities[i]["gtfs_layer"],
                    'category_field':[],
                    'categories': None,
                    'filter_field': 'headway',
                    'filter_iterations': [">=0","<=30","<=20"],
                    'output_names':["pt_gtfs_any","pt_gtfs_freq_30","pt_gtfs_freq_20"],
                    'notes':None
                }
            },
            "sample_point_analyses":{
                # evaluate final PT access measure considered across both OSM or GTFS (which may be null)
                'Evaluate binary access':{
                    ','.join(['x.sp_access_fresh_food_market_binary',
                              'x.sp_access_convenience_binary',
                              'x.sp_access_pt_osm_any_binary',
                              'x.sp_access_public_open_space_any_binary',
                              'x.sp_access_public_open_space_large_binary',
                              'x.sp_access_pt_gtfs_any_binary',
                              'x.sp_access_pt_gtfs_freq_30_binary',
                              'x.sp_access_pt_gtfs_freq_20_binary']):{
                        'columns':['x.sp_nearest_node_fresh_food_market',
                                   'x.sp_nearest_node_convenience',
                                   'x.sp_nearest_node_pt_osm_any',
                                   'x.sp_nearest_node_public_open_space_any',
                                   'x.sp_nearest_node_public_open_space_large',
                                   'x.sp_nearest_node_pt_gtfs_any',
                                   'x.sp_nearest_node_pt_gtfs_freq_30',
                                   'x.sp_nearest_node_pt_gtfs_freq_20'],
                        'formula':"(x <= accessibility_distance).astype('int64')",
                        'axis':1}
                },
                # evaluate final PT access measure considered across both OSM or GTFS (which may be null)
                'Best PT (any) access score':{
                    'sp_access_pt_any_binary':{
                        'columns':['x.sp_access_pt_osm_any_binary',
                                    'x.sp_access_pt_gtfs_any_binary'],
                        'formula':"x.max()",
                        'axis':1}
                },
                # evaluate sum of binary scores, ignoring nulls
                'Daily living score':{
                    'sp_daily_living_score':{
                        'columns':['sp_access_fresh_food_market_binary',
                                  'sp_access_convenience_binary',
                                  'sp_access_pt_any_binary'],
                        'formula':"x.sum()",
                        'axis':1}
                },
                # evaluate sum of binary scores, ignoring nulls
                'Walkability index':{
                    ','.join(['sp_z_daily_living_score',
                               'sp_z_local_nh_population_density',
                               'sp_z_local_nh_intersection_density']):{
                        'columns':['sp_daily_living_score',
                                   'sp_local_nh_avg_pop_density',
                                   'sp_local_nh_avg_intersection_density'],
                        'formula':"(x-x.mean())/x.std()",
                        'axis':0},
                    'sp_walkability_index':{
                        'columns':['z_sp_daily_living_score',
                                 'z_sp_local_nh_avg_pop_density',
                                 'z_sp_local_nh_avg_intersection_density'],
                        'formula':"x.sum()",
                        'axis':1},
                },
            }
        }
        
        # serializing json, write to file
        with open(f"configuration/{city}.py", "w") as file:
            file.write(f"""# Global Indicators project\n# Generated configuration file for {city.title()}\n# {time.strftime("%Y-%m-%d")}\n\nconfig={city_config}""")
    
    # prepare cities configuration json file for aggregation
    print("Generate cities aggregation configuration json file")
    startTime = time.time()
    
    gpkgNames = {}
    cities_config = {}
    
    for i in range(len(cities)):
        city = cities[i]["cityname"]
        region = cities[i]["region"]
        
        gpkgName = {city: f"{city}_{region}_{project_year}_{neighbourhood_distance}m_buffer_output{output_date}.gpkg"}
        gpkgNames.update(gpkgName)
    
    cities_config = {"gpkgNames": gpkgNames}
    cities_config.update(cities_parameters)
    cities_config.update({"hex_fieldNames": hex_fieldNames})
    cities_config.update({"city_fieldNames": city_fieldNames})
    
    with open("configuration/cities.json", "w") as write_file:
        json.dump(cities_config, write_file, indent=4)
    
    endTime = time.time() - startTime
    print(f"All study region configuration file were generated, total time is : {(endTime/3600):.2f} hours or {endTime:.2f} seconds")
