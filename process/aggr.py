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
import time
import pandas as pd
import geopandas as gpd
import sys
import setup_aggr as sa # module for all aggregation functions used in this notebook
import setup_config as sc # import project config parameters


if __name__ == '__main__':
    # use the script from command line, like 'python aggr.py cities.json'
    # the script will read pre-prepared sample point indicators from geopackage of each city

    startTime = time.time()
    print('Process aggregation for hex-level indicators.')
    # get the work directory
    dirname = os.path.dirname(__file__)
    jsonFile = './configuration/' + sys.argv[1]

    # read all cities configuration json file (cities.json)
    try:
        jsonPath = os.path.join(dirname, jsonFile)
        with open(jsonPath) as json_file:
            config = json.load(json_file)
    except Exception as e:
        print('Failed to read json file.')
        print(e)

    # specify input and output folder
    folder = config['folder']
    input_folder = config['input_folder']
    # read city names from config
    cities = [sc.cities[i]['cityname'] for i in range(len(sc.cities))]
    print('Cities:{}'.format(cities))

    # create the path of 'global_indicators_hex_250m.gpkg'
    # this is the geopackage to store the hexagon-level spatial indicators for each city
    gpkgOutput_hex250 = os.path.join(dirname, folder,
                                     config['output_hex_250m'])

    # read pre-prepared sample point stats of each city from disk
    gpkgInput_ori = []
    for gpkg in list(config['gpkgNames'].values()):
        gpkgInput_ori.append(os.path.join(dirname, input_folder, gpkg))

    # calculate within-city indicators weighted by sample points for each city
    # calc_hexes_pct_sp_indicators take sample point stats within each city as input and aggregate up to hex-level indicators
    # by calculating the mean of sample points stats within each hex
    print('Calculate hex-level indicators weighted by sample points within each city')
    for index, gpkgInput in enumerate(gpkgInput_ori):
        sa.calc_hexes_pct_sp_indicators(gpkgInput, gpkgOutput_hex250, cities[index],
                   config['samplepointResult'], config['hex250'])

    # calculate within-city zscores indicators for each city
    # calc_hexes_zscore_walk take the zsocres of the hex-level indicators generated using calc_hexes_pct_sp_indicators function
    # to create daily living and walkability scores
    print('Calculate hex-level indicators zscores relative to all cities.')
    sa.calc_hexes_zscore_walk(gpkgOutput_hex250, cities)


    # create the path of 'global_indicators_city.gpkg'
    gpkgOutput_cities = os.path.join(dirname, folder,
                                     config['global_indicators_city'])

    # prepare aggregation across all cities
    print('Prepare aggregation for city-level indicators.')

    # calculate city-level indicators weighted by population
    # calc_cities_pop_pct_indicators function take hex-level indicators and pop estimates of each city as input
    # then aggregate hex-level to city-level indicator by summing all the population weighted hex-level indicators
    print('Calculate city-level indicators weighted by city population:')
    for index, gpkgInput in enumerate(gpkgInput_ori):
        sa.calc_cities_pop_pct_indicators(gpkgOutput_hex250, cities[index], gpkgInput, gpkgOutput_cities)


    print('Time is: {}'.format(time.time() - startTime))
    print('finished.')
