################################################################################
# Script: aggr.py
# Description: This script is for preparing all within and across city indicators
# This script should be run after when the sample point stats are prepared for all cities (sp.py)
# use this is script to get all the final output for both within-city and across-city indicator

# Two outputs:
# 1. global_indicators_hex_250m.gpkg
# 2. global_indicators_city.gpkg

################################################################################

import json
import os
import sys
import time
from tqdm import tqdm

import setup_aggr as sa  # module for all aggregation functions used in this notebook

if __name__ == "__main__":
    # use the script from command line, like 'python aggr.py'
    # the script will read pre-prepared sample point indicators from geopackage of each city
    
    startTime = time.time()
    print("Process aggregation for hex-level indicators.")
    
    # Establish key configuration parameters
    folder_path = os.path.abspath("")
    config = sa.cities_config
    output_folder = config["output_folder"]
    cities = list(config["gpkgNames"].keys())
    cities_count = len(cities)
    gpkg_output_hex = config["output_hex_250m"].replace('.gpkg',f'_{time.strftime("%Y-%m-%d")}.gpkg')
    gpkg_output_cities = config["global_indicators_city"].replace('.gpkg',f'_{time.strftime("%Y-%m-%d")}.gpkg')
    
    print(f"\nCities: {cities}\n")
    
    # Create the path of 'global_indicators_hex_250m.gpkg'
    # This is the geopackage to store the hexagon-level spatial indicators for each city
    # The date of output processing is appended to the output file to differentiate from 
    # previous results, if any  (yyyy-mm-dd format)
    gpkg_output_hex = os.path.join(folder_path, output_folder, gpkg_output_hex)
    
    if not os.path.exists(os.path.dirname(gpkg_output_hex)):
        os.makedirs(os.path.dirname(gpkg_output_hex))
    
    # read pre-prepared sample point stats of each city from disk
    gpkg_inputs = []
    for gpkg in list(config["gpkgNames"].values()):
        gpkg_inputs.append(os.path.join(folder_path, output_folder, gpkg))
    
    # calculate within-city indicators weighted by sample points for each city
    # calc_hexes_pct_sp_indicators take sample point stats within each city as
    # input and aggregate up to hex-level indicators by calculating the mean of
    # sample points stats within each hex
    print("\nCalculate hex-level indicators weighted by sample points within each city")
    for i, gpkg_input in enumerate(tqdm(gpkg_inputs)):        
        sa.calc_hexes_pct_sp_indicators(gpkg_input, gpkg_output_hex, 
                cities[i], config["samplepointResult"], config["hex250"])
    
    # calculate within-city zscores indicators for each city
    # calc_hexes_zscore_walk take the zsocres of the hex-level indicators
    # generated using calc_hexes_pct_sp_indicators function to create daily
    # living and walkability scores
    print("\nCalculate hex-level indicators zscores relative to all cities.")
    sa.calc_hexes_zscore_walk(gpkg_output_hex, cities)
    
    print("\nCreate combined layer of all cities hex grids, to facilitate grouped analyses and mapping")
    sa.combined_city_hexes(gpkg_inputs, gpkg_output_hex, cities)
    
    # calculate city-level indicators weighted by population
    # calc_cities_pop_pct_indicators function take hex-level indicators and
    # pop estimates of each city as input then aggregate hex-level to city-level
    # indicator by summing all the population weighted hex-level indicators
    print("Calculate city-level indicators weighted by city population:")
    gpkg_output_cities = os.path.join(folder_path, output_folder, gpkg_output_cities)
    # in addition to the population weighted averages, unweighted averages are also included to reflect
    # the spatial distribution of key walkability measures (regardless of population distribution)
    # as per discussion here: https://3.basecamp.com/3662734/buckets/11779922/messages/2465025799
    extra_unweighted_vars = ['local_nh_population_density','local_nh_intersection_density','local_daily_living',
      'local_walkability',
      'all_cities_z_nh_population_density','all_cities_z_nh_intersection_density','all_cities_z_daily_living',
      'all_cities_walkability']
    for i, gpkg_input in enumerate(tqdm(gpkg_inputs)):
        if i==0:
            all_cities_combined = sa.calc_cities_pop_pct_indicators(gpkg_output_hex, cities[i], 
                gpkg_input, gpkg_output_cities,extra_unweighted_vars) 
        else:
            all_cities_combined = all_cities_combined.append(sa.calc_cities_pop_pct_indicators(gpkg_output_hex, 
                cities[i], gpkg_input, gpkg_output_cities,extra_unweighted_vars))
    
    all_cities_combined = all_cities_combined.sort_values(['Continent', 'Country','City'])
    all_cities_combined.to_file(gpkg_output_cities, layer='all_cities_combined', driver="GPKG")
    all_cities_combined[[x for x in all_cities_combined.columns if x!='geometry']]\
        .to_csv(gpkg_output_cities.replace('gpkg','csv'),index=False)
    print(f"Time is: {(time.time() - startTime)/60.0:.02f} mins")
    print("finished.")
