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

# define project parameters
# list of cities that are needed to be set up
cities = [
    # {"cityname": "adelaide", "region": "au", "crs": "epsg:7845"},
    # {"cityname": "auckland", "region": "nz", "crs": "epsg:2193"},
    # {"cityname": "baltimore", "region": "us", "crs": "epsg:32618"},
    # {"cityname": "bangkok", "region": "th", "crs": "epsg:32647"},
    # {"cityname": "barcelona", "region": "es", "crs": "epsg:25831"},
    # {"cityname": "belfast", "region": "gb", "crs": "epsg:29902"},
    # {"cityname": "bern", "region": "ch", "crs": "epsg:32633"},
    # {"cityname": "chennai", "region": "in", "crs": "epsg:32644"},
    # {"cityname": "cologne", "region": "de", "crs": "epsg:32631"},
    # {"cityname": "ghent", "region": "be", "crs": "epsg:32631"},
    # {"cityname": "graz", "region": "at", "crs": "epsg:32633"},
    # {"cityname": "hanoi", "region": "vn", "crs": "epsg:32648"},
    # {"cityname": "hong_kong", "region": "hk", "crs": "epsg:32650"},
    # {"cityname": "lisbon", "region": "pt", "crs": "epsg:3763"},
    # {"cityname": "melbourne", "region": "au", "crs": "epsg:7845"},
    # {"cityname": "mexico_city", "region": "mx", "crs": "epsg:32614"},
     {"cityname": "odense", "region": "dk", "crs": "epsg:32632"},
     {"cityname": "olomouc", "region": "cz", "crs": "epsg:32633"},
    # {"cityname": "phoenix", "region": "us", "crs": "epsg:32612"},
    # {"cityname": "sao_paulo", "region": "br", "crs": "epsg:32723"},
    # {"cityname": "seattle", "region": "us", "crs": "epsg:32610"},
    # {"cityname": "sydney", "region": "au", "crs": "epsg:7845"},
    # {"cityname": "valencia", "region": "es", "crs": "epsg:25830"},
    # {"cityname": "vic", "region": "es", "crs": "epsg:25831"},
]


project_year = 2019  # Year that the current indicators are targetting
osm_input_date = 20190902  # Date at which OSM download was current
output_date = time.strftime('%Y%m%d')  # Date at which the output date were generated
study_buffer = 10000  # Study region buffer, to account for edge effects, in meters
distance = 1600  # sausage buffer network size, in meters

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
    "samplepointResult": "samplePointsData",
}

# specify study region sample point stats field name
# these are sample point variables in 'samplePointsData_withoutNan' layer within study region input gpkg
samplePoint_fieldNames = {
    "sp_local_nh_avg_pop_density": "sp_local_nh_avg_pop_density",
    "sp_local_nh_avg_intersection_density": "sp_local_nh_avg_intersection_density",
    "sp_supermarket_dist_m": "sp_supermarket_dist_m",
    "sp_access_supermarket_binary": "sp_access_supermarket_binary",
    "sp_convenience_dist_m": "sp_convenience_dist_m",
    "sp_access_convenience_binary": "sp_access_convenience_binary",
    "sp_pt_dist_m": "sp_pt_dist_m",
    "sp_access_pt_binary": "sp_access_pt_binary",
    "sp_pos_dist_m": "sp_pos_dist_m",
    "sp_access_pos_binary": "sp_access_pos_binary",
    "sp_daily_living_score": "sp_daily_living_score",
    "sp_zscore_local_nh_avgpopdensity": "sp_zscore_local_nh_avgpopdensity",
    "sp_zscore_local_nh_avgintdensity": "sp_zscore_local_nh_avgintdensity",
    "sp_zscore_daily_living_score": "sp_zscore_daily_living_score",
    "sp_walkability_index": "sp_walkability_index",
}

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
    "geometry": "geometry",
}

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
    "geometry": "geometry",
}


if __name__ == "__main__":
    # prepare city specific configuration json file
    print("Generate study region configuration json file")
    startTime = time.time()

    for i in range(len(cities)):
        # generate dict of study region input datasource parameters
        city = cities[i]["cityname"]
        region = cities[i]["region"]
        to_crs = cities[i]["crs"]

        gpkg_template = "{city}_{region}_{project_year}_{distance}m_buffer_output{output_date}.gpkg"
        graphml_template = "{city}_{region}_{project_year}_{study_buffer}m_pedestrian_osm_{osm_input_date}.graphml"
        gp_template = "{city}_{region}_{project_year}_{study_buffer}m_pedestrian_osm_{osm_input_date}_proj.graphml"
        city_config = {
            "study_region": "{city}".format(city=city),
            "to_crs": "{crs}".format(crs=to_crs),
            "geopackagePath": "{city}_{region}_{project_year}_{distance}m_buffer.gpkg".format(
                city=city, region=region, project_year=project_year, distance=distance
            ),
            "geopackagePath_output": gpkg_template.format(
                city=city, region=region, project_year=project_year, distance=distance, output_date=output_date
            ),
            "graphmlName": graphml_template.format(
                city=city,
                region=region,
                project_year=project_year,
                study_buffer=study_buffer,
                osm_input_date=osm_input_date,
            ),
            "graphmlProj_name": gp_template.format(
                city=city,
                region=region,
                project_year=project_year,
                study_buffer=study_buffer,
                osm_input_date=osm_input_date,
            ),
            "folder": "data/input",
            "tempCSV": "nodes_pop_intersect_density_{city}.csv".format(city=city),
        }
        # serializing json, write to file
        with open("configuration/{city}.json".format(city=city), "w") as write_file:
            json.dump(city_config, write_file, indent=4)

    # prepare cities configuration json file for aggregation
    print("Generate cities aggregation configuration json file")
    startTime = time.time()

    gpkgNames = {}
    cities_config = {}

    for i in range(len(cities)):
        city = cities[i]["cityname"]
        region = cities[i]["region"]

        gpkgName = {
            "{city}".format(
                city=city
            ): "{city}_{region}_{project_year}_{distance}m_buffer_output{output_date}.gpkg".format(
                city=city, region=region, project_year=project_year, distance=distance, output_date=output_date
            )
        }
        gpkgNames.update(gpkgName)

    cities_config = {"gpkgNames": gpkgNames}
    cities_config.update(cities_parameters)
    cities_config.update({"hex_fieldNames": hex_fieldNames})
    cities_config.update({"city_fieldNames": city_fieldNames})

    with open("configuration/cities.json", "w") as write_file:
        json.dump(cities_config, write_file, indent=4)

    endTime = time.time() - startTime
    print(
        "All study region configuration file were generated, total time is : {0:.2f} hours or {1:.2f} seconds".format(
            endTime / 3600, endTime
        )
    )
