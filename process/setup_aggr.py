################################################################################
# Module: setup_aggre.py
# Description: this module contains functions to set up within and accross city indicators

################################################################################

import json
import os
import time
import pandas as pd
import geopandas as gpd
import sys

def calc_hexes(gpkg_input, gpkg_output, city, layer_samplepoint, layer_hex,
               config):
    """
    Caculate sample point weighted hexagon-level indicators within each city,
    and save to output geopackage

    These indicators include (pecentage of sample points within 500m access to destinations):
        "pct_access_500m_supermarkets"
        "pct_access_500m_convenience"
        "pct_access_500m_pt_any"
        "pct_access_500m_public_open_space"

    Parameters
    ----------
    gpkg_input: str
        file path of input geopackage
    gpkg_output: str
        file path of output geopackage
    city: str
        name of a city
    layer_samplepoint: str
        the layer of sample point layer
    layer_hex: str
        the name of hex layer
    config: dict
        dict read from configeration file

    Returns
    -------
    list, list of GeoDataFrame
    """
    # read input geopackage with processed sample point and hex layer
    gdf_samplepoint = gpd.read_file(gpkg_input, layer=layer_samplepoint)
    gdf_hex = gpd.read_file(gpkg_input, layer=layer_hex)

    # calculate the number of urban sample point for each hex based on the hex_id
    samplepoint_count = gdf_samplepoint['hex_id'].value_counts()
    # join the sample point count column to hex layer based on hex_id
    gdf_hex_new = gdf_hex.join(samplepoint_count, how='inner', on='index')
    gdf_hex_new.rename(columns={'hex_id': "urban_sample_point_count"},
                       inplace=True)

    # read sample point indicator field names from configeration file
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
    #  read hex indicator field names from configeration file
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
    # perform aggregation functions to calculate hex level indicators
    gdf_hex_new = aggregation(
        gdf_hex_new, gdf_samplepoint,
        list(zip(fieldNames_from_samplePoint, fieldNames2hex)))

    #  read hex indicator field names from configeration file
    fields = [
        config['hex_fieldNames']['pct_access_500m_supermarkets'],
        config['hex_fieldNames']['pct_access_500m_convenience'],
        config['hex_fieldNames']['pct_access_500m_pt_any'],
        config['hex_fieldNames']['pct_access_500m_public_open_space']
    ]
    # change accessibility to Percentage
    gdf_hex_new[fields] = gdf_hex_new[fields] * 100

    gdf_hex_new = organiseColumnName(gdf_hex_new,
                                     list(config['hex_fieldNames'].values()))

    if config['hex_fieldNames'][
            'study_region'] not in gdf_hex_new.columns.to_list():
        gdf_hex_new[config['hex_fieldNames']['study_region']] = city
    # save the gdf_hex_new to geopackage
    gdf_hex_new.to_file(gpkg_output, layer=city, driver='GPKG')
    return  gdf_hex_new


def calc_hexes_citieslevel(gpkg_output, cityNames, config):
    """
    Calculate zscore of hexagon-level indicators within each city, and save to output geopackage

    These indicators include (z-score of population weighted indicators relative to all cities):
        "all_cities_z_nh_population_density",
        "all_cities_z_nh_intersection_density",
        "all_cities_z_daily_living",
        "all_cities_walkability"

    Parameters
    ----------
    gpkg_output: str
        file path of output geopackage
    cityNames: list
        all the city names
    config: dict
        dict read from configeration file

    Returns
    -------
    none
    """
    # read and append all cities hex layer from the output geopackage
    gdf_layers = []
    for i in cityNames:
        try:
            gdf = gpd.read_file(gpkg_output, layer=i)
            gdf = gdf.reindex(columns=sorted(gdf.columns))
            gdf_layers.append(gdf)
        except ValueError as e:
            print(e)

    # concatenate all cities hex layers into one a dataframe
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
    # calculate the zscores of indicators accross cities
    for index, layer in enumerate(gdf_layers):
        for field_zip in fieldNames_zip:
            mean, std = getMeanStd(all_cities_hex_df, field_zip[0])
            layer[field_zip[1]] = (layer[field_zip[0]] - mean) / std
        # calculate the accross-city walkability index by summing all zscore indicators
        layer[config['hex_fieldNames']
              ['all_cities_walkability']] = layer[fieldNames_new].sum(axis=1)
        # save the indicators to out the output geopackage
        layer.to_file(gpkg_output, layer=cityNames[index], driver='GPKG')


def calc_city(gpkg_hex_250m, city, gpkg_input, config, gpkg_output):
    """
    Calculate population-weighted city-level indicators accross all cities,
    and save to output geopackage

    These indicators include:
        'pop_pct_access_500m_supermarkets',
        'pop_pct_access_500m_convenience',
        'pop_pct_access_500m_pt_any',
        'pop_pct_access_500m_public_open_space',
        'pop_nh_pop_density',
        'pop_nh_intersection_density',
        'pop_daily_living',
        'pop_walkability'


    Parameters
    ----------
    gpkg_hex_250m: str
        file path of accross-ctiy hexagon-level indicators
    city: str
        name of a city
    gpkg_input: str
        file path of input geopackage
    config: dict
        dict read from configeration file
    gpkg_output: str
        file path of output geopackage

    Returns
    -------
    list, list of GeoDataFrame
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

    # hex-level field names from input gpkg
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
    # new file names for population-weighted city-level indicators
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
    return gdf_study_region


def calc_city_citieslevel(gpkg_input, cityNames, config):
    """
    Calculate zscore of city-level indicators accross all cities,
    and save to output geopackage

    These indicators include (z-score of population weighted indicators relative to all cities):
        "all_cities_pop_z_nh_population_density",
        "all_cities_pop_z_nh_intersection_density",
        "all_cities_z_daily_living",
        "all_cities_walkability"

    Parameters
    ----------
    gpkg_input: str
        file path of input geopackage
    cityNames: list
        all the city names
    config: dict
        dict read from configeration file

    Returns
    -------
    none
    """

    gdf_layers = []
    for i in cityNames:
        try:
            gdf = gpd.read_file(gpkg_input, layer=i)
            gdf = gdf.reindex(columns=sorted(gdf.columns))
            gdf_layers.append(gdf)
        except ValueError as e:
            print(e)

    # combine all ciities layers into one dataframe (all_cities_hex_df) according to gdf_layers
    all_cities_hex_df = pd.concat(gdf_layers, ignore_index=True)

    # these are field names that already exisited within each city layer
    fieldNames = [
        config['city_fieldNames']['pop_nh_pop_density'],
        config['city_fieldNames']['pop_nh_intersection_density'],
        config['city_fieldNames']['pop_daily_living']
    ]

    # specify new field names for the zscore indicators
    # they represents pop density, intersection density, and daily living score
    fieldNames_new = [
        config['city_fieldNames']['all_cities_pop_z_nh_population_density'],
        config['city_fieldNames']['all_cities_pop_z_nh_intersection_density'],
        config['city_fieldNames']['all_cities_pop_z_daily_living']
    ]

    fieldNames_zip = list(zip(fieldNames, fieldNames_new))

    for index, layer in enumerate(gdf_layers):
        for field_zip in fieldNames_zip:
            # get mean and standard deviation of all city-level indicator
            mean, std = getMeanStd(all_cities_hex_df, field_zip[0])
            # calculate the zscore of city-level indicator
            layer[field_zip[1]] = (layer[field_zip[0]] - mean) / std

        # sum all three indicators to get walkability score
        layer[config['city_fieldNames']
              ['all_cities_walkability']] = layer[fieldNames_new].sum(axis=1)
        layer = layer.reindex(columns=sorted(layer.columns))
        layer.to_file(gpkg_input, layer=cityNames[index], driver='GPKG')


def aggregation(gdf_hex, gdf_samplePoint, fieldNames):
    """
    Aggregating sample-point level indicators to hexagon level within city
    by averaging sample-point stats within a hexagon

    Parameters
    ----------
    gdf_hex: GeoDataFrame
        GeoDataFrame of hexagon
    gdf_samplePoint: GeoDataFrame
        GeoDataFrame of sample point
    fieldNames: list(zip)
        fieldNames of sample point and hexagon indicators

    Returns
    -------
    GeoDataFrame
    """
    # loop over each indicators field names for sample point and hexagon
    for names in fieldNames:
        # calculate the mean of sample point stats within each hexagon based on the hex id
        df = gdf_samplePoint[['hex_id', names[0]]].groupby('hex_id').mean()
        # join the indicator results back to hex GeoDataFrame
        gdf_hex = gdf_hex.join(df, how='left', on='ind\ex')
        # rename the fieldNames for hex-level indicators
        gdf_hex.rename(columns={names[0]: names[1]}, inplace=True)
    return gdf_hex


def aggregation_city(input_gdf, out_gdf, config, fieldNames):
    """
    Aggregating hexagon level indicators to city level by weighted population


    Parameters
    ----------
    input_gdf: GeoDataFrame
        GeoDataFrame of input hexagon
    out_gdf: GeoDataFrame
        GeoDataFrame of output city
    config: dict
        dict read from configeration file
    fieldNames: list(zip)
        fieldNames of hex-level and city-level indicators

    Returns
    -------
    GeoDataFrame
    """
    # loop over each indicators field names of input and output gdf
    for field in fieldNames:
        # calculate the population weighted indicators based on input hexagon layer
        # sum to aggregate up to the city level
        out_gdf[field[1]] = (input_gdf[config['pop_est']] * input_gdf[field[0]]
                             ).sum() / (input_gdf[config['pop_est']].sum())
    return out_gdf


def organiseColumnName(gdf, fieldNames):
    """
    Organise the gdf column name to make it match the desired result
    note: at this stage, some of the fields haven't had number

    Parameters
    ----------
    gdf: GeoDataFrame
    fieldNames: list
        list of desired field names

    Returns
    -------
    GeoDataFrame
    """
    fieldNamesOld = gdf.columns.to_list()
    fields = []
    # change old gdf columns names to new desired columns names
    for i in fieldNamesOld:
        if i in fieldNames:
            fields.append(i)
    return gdf[fields].copy()


def getMeanStd(gdf, columnName):
    """
    Calculate mean and std from the combined dataframe of all cities

    Parameters
    ----------
    gdf: GeoDataFrame
    columnName: str

    Returns
    -------
    mean, std
    """
    mean = gdf[columnName].mean()
    std = gdf[columnName].std()
    return mean, std
