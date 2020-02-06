"""
    after preparing sample point geopackages for all cities,
    use this is script to get all the final output
    "global_indicators_hex_250m.gpkg" and
    "global_indicators_city.gpkg"
"""
import json
import os
import time
import pandas as pd
import geopandas as gpd
import sys


def aggregation(gdf_hex, gdf_samplePoint, fieldNames):
    """
    calculate aggregation for hex

    Arguments:
        gdf_hex {geopandas} -- hex
        gdf_samplePoint {geopandas} -- sample point
        fieldNames {list(zip)} -- fieldNames from sample point and hex
    """
    for names in fieldNames:
        df = gdf_samplePoint[['hex_id', names[0]]].groupby('hex_id').mean()
        gdf_hex = gdf_hex.join(df, how='left', on='index')
        gdf_hex.rename(columns={names[0]: names[1]}, inplace=True)
    return gdf_hex


def aggregation_city(input_gdf, out_gdf, config, fieldNames):
    """create aggregation result for city from hexes
    Arguments:
        input_gdf {geodataframe} -- [hex]
        out_gdf {geodataframe} -- [city]
        config {dict} -- dict read from json file
        fieldNames {list} -- [zipped input and output fieldnames]
    """
    for field in fieldNames:
        out_gdf[field[1]] = (input_gdf[config['pop_est']] * input_gdf[field[0]]
                             ).sum() / (input_gdf[config['pop_est']].sum())
    return out_gdf


def organiseColumnName(gdf, fieldNames):
    """organise the gdf column name to make it match the desired result
    note: at this stage, some of the fields haven't had number
    Arguments:
        gdf {geodataframe} -- the hex should be rename the column
        fieldNames {list} -- all the desired field names
    """
    fieldNamesOld = gdf.columns.to_list()
    fields = []
    for i in fieldNamesOld:
        if i in fieldNames:
            fields.append(i)
    return gdf[fields].copy()


def getMeanStd(gdf, columnName):
    """
    calculate mean and std from the big dataframe of all cities

    Arguments:
        gdf {[geodataframe]} -- [all cities]
        columnName {[str]} -- [field name]
    """
    mean = gdf[columnName].mean()
    std = gdf[columnName].std()
    return mean, std


def calc_hexes(gpkg_input, gpkg_output, city, layer_samplepoint, layer_hex,
               config):
    """create aggregation fields on hexes in a city

    Arguments:
        gpkg_input {geopackage} -- full path of input geopackage
        gpkg_output {geopackage} -- full path of "global_indicators_hex_250m.gpkg"
        city {str} -- one of the city names, such as 'odense'
        layer_samplepoint {str} -- the layer name of sample point
        layer_hex {str} -- the layer name of hex
        config {dict} -- dict read from json file

    """
    # input geopackage, read processed sample point and hex
    gdf_samplepoint = gpd.read_file(gpkg_input, layer=layer_samplepoint)
    gdf_hex = gpd.read_file(gpkg_input, layer=layer_hex)

    # calculate all the "urban_sample_point_count" for each hex
    samplepoint_count = gdf_samplepoint['hex_id'].value_counts()
    gdf_hex_new = gdf_hex.join(samplepoint_count, how='inner', on='index')
    gdf_hex_new.rename(columns={'hex_id': "urban_sample_point_count"},
                       inplace=True)

    # calculate aggregation for hex
    fieldNames_from_samplePoint = [
        config['samplePoint_fieldNames']['sp_nearest_node_supermarket_binary'],
        config['samplePoint_fieldNames']['sp_nearest_node_convenience_binary'],
        config['samplePoint_fieldNames']['sp_nearest_node_pt_binary'],
        config['samplePoint_fieldNames']['sp_nearest_node_pos_binary'],
        config['samplePoint_fieldNames']['sp_local_nh_avg_pop_density'],
        config['samplePoint_fieldNames']
        ['sp_local_nh_avg_intersection_density'],
        config['samplePoint_fieldNames']['sp_daily_living_score'],
        config['samplePoint_fieldNames']['sp_walkability_index']
    ]

    fieldNames2hex = [
        config['hex_fieldNames']['pct_access_500m_supermarkets'],
        config['hex_fieldNames']['pct_access_500m_convenience'],
        config['hex_fieldNames']['pct_access_500m_pt_any'],
        config['hex_fieldNames']['pct_access_500m_public_open_space'],
        config['hex_fieldNames']['local_nh_population_density'],
        config['hex_fieldNames']['local_nh_intersection_density'],
        config['hex_fieldNames']['local_daily_living'],
        config['hex_fieldNames']['local_walkability']
    ]

    gdf_hex_new = aggregation(
        gdf_hex_new, gdf_samplepoint,
        list(zip(fieldNames_from_samplePoint, fieldNames2hex)))

    # change accessibility to Percentage
    fields = [
        config['hex_fieldNames']['pct_access_500m_supermarkets'],
        config['hex_fieldNames']['pct_access_500m_convenience'],
        config['hex_fieldNames']['pct_access_500m_pt_any'],
        config['hex_fieldNames']['pct_access_500m_public_open_space']
    ]
    gdf_hex_new[fields] = gdf_hex_new[fields] * 100

    gdf_hex_new = organiseColumnName(gdf_hex_new,
                                     list(config['hex_fieldNames'].values()))

    if config['hex_fieldNames'][
            'study_region'] not in gdf_hex_new.columns.to_list():
        gdf_hex_new[config['hex_fieldNames']['study_region']] = city
    # save the gdf_hex_new to geopackage
    gdf_hex_new.to_file(gpkg_output, layer=city, driver='GPKG')


def calc_hexes_citieslevel(gpkg_output, cityNames, config):
    """create fields across cities on hexes, such as
        "all_cities_z_nh_population_density",
        "all_cities_z_nh_intersection_density",
        "all_cities_z_daily_living",
        "all_cities_walkability"

    Arguments:
        gpkg_output {geopackage} -- full path of "global_indicators_hex_250m.gpkg"
        cityNames {list} -- all the city names(layer name in geopackage)
        config {dict} -- dict read from json file
    """

    gdf_layers = []
    for i in cityNames:
        try:
            gdf = gpd.read_file(gpkg_output, layer=i)
            gdf = gdf.reindex(columns=sorted(gdf.columns))
            gdf_layers.append(gdf)
        except ValueError as e:
            print(e)

    # create a big dataframe(all_cities_hex_df) according to gdf_layers
    all_cities_hex_df = pd.concat(gdf_layers, ignore_index=True)

    fieldNames = [
        config['hex_fieldNames']['local_nh_population_density'],
        config['hex_fieldNames']['local_nh_intersection_density'],
        config['hex_fieldNames']['local_daily_living']
    ]

    fieldNames_new = [
        config['hex_fieldNames']['all_cities_z_nh_population_density'],
        config['hex_fieldNames']['all_cities_z_nh_intersection_density'],
        config['hex_fieldNames']['all_cities_z_daily_living']
    ]

    fieldNames_zip = list(zip(fieldNames, fieldNames_new))

    for index, layer in enumerate(gdf_layers):
        for field_zip in fieldNames_zip:
            mean, std = getMeanStd(all_cities_hex_df, field_zip[0])
            layer[field_zip[1]] = (layer[field_zip[0]] - mean) / std
        # sum all three new fields
        layer[config['hex_fieldNames']
              ['all_cities_walkability']] = layer[fieldNames_new].sum(axis=1)
        layer.to_file(gpkg_output, layer=cityNames[index], driver='GPKG')


def calc_city(gpkg_hex_250m, city, gpkg_input, config, gpkg_output):
    """create aggregation fields on a study region

    Arguments:
        gpkg_hex_250m {str} -- full path of "global_indicators_hex_250m.gpkg"
        city {str} -- city name(layer name) such as 'odense'
        gpkg_input {str} -- full path of original geopackage
        config {dict} -- dict read from json file
        gpkg_output {str} -- full path of 'global_indicators_city.gpkg'
    """
    gdf_hex = gpd.read_file(gpkg_hex_250m, layer=city)

    gdf_hex_origin = gpd.read_file(gpkg_input, layer=config["hex250"])
    gdf_study_region = gpd.read_file(gpkg_input,
                                     layer=config["urban_study_region"])
    # join pop_est from original hex to processed hex
    gdf_hex = gdf_hex.join(gdf_hex_origin.set_index('index'),
                           on='index',
                           how='left',
                           rsuffix='_origin')
    # or
    # gdf_hex=pd.merge(gdf_hex,gdf_hex_origin,on='index',how='left',suffixes=('','_origin'))

    gdf_study_region[
        config['city_fieldNames']['urban_sample_point_count']] = gdf_hex[
            config['hex_fieldNames']['urban_sample_point_count']].sum()

    fieldNames = [
        config['hex_fieldNames']['pct_access_500m_supermarkets'],
        config['hex_fieldNames']['pct_access_500m_convenience'],
        config['hex_fieldNames']['pct_access_500m_pt_any'],
        config['hex_fieldNames']['pct_access_500m_public_open_space'],
        config['hex_fieldNames']['local_nh_population_density'],
        config['hex_fieldNames']['local_nh_intersection_density'],
        config['hex_fieldNames']['local_daily_living'],
        config['hex_fieldNames']['local_walkability']
    ]

    fieldNames_new = [
        config['city_fieldNames']['pop_pct_access_500m_supermarkets'],
        config['city_fieldNames']['pop_pct_access_500m_convenience'],
        config['city_fieldNames']['pop_pct_access_500m_pt_any'],
        config['city_fieldNames']['pop_pct_access_500m_public_open_space'],
        config['city_fieldNames']['pop_nh_pop_density'],
        config['city_fieldNames']['pop_nh_intersection_density'],
        config['city_fieldNames']['pop_daily_living'],
        config['city_fieldNames']['pop_walkability']
    ]

    gdf_study_region = aggregation_city(gdf_hex, gdf_study_region, config,
                                        list(zip(fieldNames, fieldNames_new)))

    gdf_study_region.to_file(gpkg_output, layer=city, driver='GPKG')


def calc_city_citieslevel(gpkg_input, cityNames, config):
    """create fields across cities on study regions

    Arguments:
        gpkg_input {str} -- full path of 'global_indicators_city.gpkg'
        cityNames {list} -- all the city layer names in gpkg_input
        config {dict} -- dict read from json file
    """

    gdf_layers = []
    for i in cityNames:
        try:
            gdf = gpd.read_file(gpkg_input, layer=i)
            gdf = gdf.reindex(columns=sorted(gdf.columns))
            gdf_layers.append(gdf)
        except ValueError as e:
            print(e)

    # create a big dataframe(all_cities_hex_df) according to gdf_layers
    all_cities_hex_df = pd.concat(gdf_layers, ignore_index=True)

    fieldNames = [
        config['city_fieldNames']['pop_nh_pop_density'],
        config['city_fieldNames']['pop_nh_intersection_density'],
        config['city_fieldNames']['pop_daily_living']
    ]

    fieldNames_new = [
        config['city_fieldNames']['all_cities_pop_z_nh_population_density'],
        config['city_fieldNames']['all_cities_pop_z_nh_intersection_density'],
        config['city_fieldNames']['all_cities_pop_z_daily_living']
    ]

    fieldNames_zip = list(zip(fieldNames, fieldNames_new))

    for index, layer in enumerate(gdf_layers):
        for field_zip in fieldNames_zip:
            mean, std = getMeanStd(all_cities_hex_df, field_zip[0])
            layer[field_zip[1]] = (layer[field_zip[0]] - mean) / std
        # sum all three new fields
        layer[config['city_fieldNames']
              ['all_cities_walkability']] = layer[fieldNames_new].sum(axis=1)
        layer = layer.reindex(columns=sorted(layer.columns))
        layer.to_file(gpkg_input, layer=cityNames[index], driver='GPKG')


if __name__ == "__main__":
    # use the script from command line, like "python process/sv_aggr.py odense.json"
    # the script will read pre-prepared sample point from geopackage of each city

    startTime = time.time()
    print('Start to process aggregation on cities.')
    # get the work directory
    dirname = os.path.dirname(__file__)
    jsonFile = "./configuration/" + sys.argv[1]

    # read json file
    try:
        jsonPath = os.path.join(dirname, jsonFile)
        with open(jsonPath) as json_file:
            config = json.load(json_file)
    except Exception as e:
        print('Failed to read json file.')
        print(e)

    folder = config['folder']
    input_folder = config['input_folder']
    # read city names from json
    cites = list(config['cityNames'].values())
    print("Cities:{}".format(cites))
    # create the path of "global_indicators_hex_250m.gpkg"
    gpkgOutput_hex250 = os.path.join(dirname, folder,
                                     config['output_hex_250m'])

    # read the path of pre-prepared sample point of each city
    gpkgInput_ori = []
    for gpkg in list(config['gpkgNames'].values()):
        gpkgInput_ori.append(os.path.join(dirname, input_folder, gpkg))

    # prepare aggregation for hexes across all cities
    print("Start to prepare aggregation for hexes across all cities.")
    for index, gpkgInput in enumerate(gpkgInput_ori):
        calc_hexes(gpkgInput, gpkgOutput_hex250, cites[index],
                   config['samplepointResult'], config['hex250'], config)

    # prepare all_cities level fields for every hex across all cities
    print("Start to prepare all_cities level fields for every hex across all cities.")
    calc_hexes_citieslevel(gpkgOutput_hex250, cites, config)

    # create the path of "global_indicators_city.gpkg"
    gpkgOutput_cities = os.path.join(dirname, folder,
                                     config['global_indicators_city'])

    # prepare aggregation for study region across all cities
    print("Start to prepare aggregation for study region across all cities.")
    for index, gpkgInput in enumerate(gpkgInput_ori):
        calc_city(gpkgOutput_hex250, cites[index], gpkgInput, config,
                  gpkgOutput_cities)

    # prepare all_cities level fields across all cities
    print("Start to prepare all_cities level fields across all cities.")
    calc_city_citieslevel(gpkgOutput_cities, cites, config)

    print('Time is: {}'.format(time.time() - startTime))
    print('finished.')
