################################################################################
# Script: aggr.py
# Description: This script is for preparing all the fields for within and accross city indicators
# This script should be run after when the sample point geopackages are prepared for all cities (sp.py)
# use this is script to get all the final output for both within-city and accross-city indicator

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
from setup_aggr import *


if __name__ == "__main__":
    # use the script from command line, like "python aggr.py odense.json"
    # the script will read pre-prepared sample point indicators from geopackage of each city

    startTime = time.time()
    print('Start to process aggregation within each city.')
    # get the work directory
    dirname = os.path.dirname(__file__)
    jsonFile = "./configuration/" + sys.argv[1]

    # read all cities configeration json file (cities.json)
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
    cites = list(config['cityNames'].values())
    print("Cities:{}".format(cites))

    # create the path of "global_indicators_hex_250m.gpkg"
    # this is the geopackage to store the hexagon-level spatial indicators for each city
    gpkgOutput_hex250 = os.path.join(dirname, folder,
                                     config['output_hex_250m'])

    # read pre-prepared sample point of each city in disk
    gpkgInput_ori = []
    for gpkg in list(config['gpkgNames'].values()):
        gpkgInput_ori.append(os.path.join(dirname, input_folder, gpkg))

    # Calculate within-city indicators weighted by sample points for each city
    # calc_hexes take sample point stats within each city as input and aggregate to hex-level indicators
    # by calculating the mean of sample points stats within each hex
    print('Calculate hex-level indicators weighted by sample points within each city')
    for index, gpkgInput in enumerate(gpkgInput_ori):
        calc_hexes(gpkgInput, gpkgOutput_hex250, cites[index],
                   config['samplepointResult'], config['hex250'], config)

    # Calculate within-city indicators zscores for each city
    # calc_hexes_citieslevel take the zsocres of the hex-level indicators generated using calc_hexes function
    # to create daily living and walkability scores
    print("Calculate hex-level indicators zscores within each city.")
    calc_hexes_citieslevel(gpkgOutput_hex250, cites, config)


    # create the path of "global_indicators_city.gpkg"
    gpkgOutput_cities = os.path.join(dirname, folder,
                                     config['global_indicators_city'])

    # prepare aggregation across all cities
    print("Start to prepare aggregation across all cities.")

    # Calculate city-level indicators weighted by city population
    # calc_city function take hex-level indicators and pop estimates of each city as input
    # then aggregate hex-level to city-level indicator by summing all the population weighted hex-level indicators
    print("Calculate city-level indicators weighted by city population:")
    for index, gpkgInput in enumerate(gpkgInput_ori):
        calc_city(gpkgOutput_hex250, cites[index], gpkgInput, config,
                  gpkgOutput_cities)

    # Calculate city-level indicators zscores across all cities.
    # calc_city_citieslevel function calculates zscore of city-level indicator accross all all cities
    print("Calculate city-level indicators zscores across all cities.")
    calc_city_citieslevel(gpkgOutput_cities, cites, config)

    print('Time is: {}'.format(time.time() - startTime))
    print('finished.')
