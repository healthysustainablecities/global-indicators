################################################################################
# Module: setup_aggr.py
# Description: this module contains functions to set up within and across city indicators

################################################################################

import geopandas as gpd
import pandas as pd

import setup_config as sc


def calc_hexes_pct_sp_indicators(gpkg_input, gpkg_output, city, layer_samplepoint, layer_hex):
    """
    Caculate sample point weighted hexagon-level indicators within each city,
    and save to output geopackage

    These indicators include:
        "pct_access_500m_fresh_food_markets"
        "pct_access_500m_convenience"
        "pct_access_500m_pt_any"
        "pct_access_500m_public_open_space"
        "local_nh_population_density"
        "local_nh_intersection_density"
        "local_daily_living"
        "local_walkability"

    Parameters
    ----------
    gpkg_input: str
        file path of input geopackage
    gpkg_output: str
        file path of output geopackage
    city: str
        the name of a city
    layer_samplepoint: str
        the name of sample point layer
    layer_hex: str
        the name of hex layer

    Returns
    -------
    list, list of GeoDataFrame
    """
    # read input geopackage with processed sample point and hex layer
    gdf_samplepoint = gpd.read_file(gpkg_input, layer=layer_samplepoint)
    gdf_hex = gpd.read_file(gpkg_input, layer=layer_hex)

    # calculate the number of urban sample point for each hex based on the hex_id
    samplepoint_count = gdf_samplepoint["hex_id"].value_counts()
    # join the sample point count column to hex layer based on hex_id
    gdf_hex_new = gdf_hex.join(samplepoint_count, how="inner", on="index")
    gdf_hex_new.rename(columns={"hex_id": "urban_sample_point_count"}, inplace=True)
    
    # perform aggregation functions to calculate sample point weighted hex level indicators
    gdf_hex_new = aggregation_sp_weighted(
        gdf_hex_new, gdf_samplepoint, list(zip(fieldNames_from_samplePoint, fieldNames2hex))
    )

    #  read hex indicator field names from configeration file
    fields = [x for x in fieldNames2hex if x.startswith('pct_access')]
    
    # change accessibility to Percentage
    gdf_hex_new[fields] = gdf_hex_new[fields] * 100

    gdf_hex_new = organiseColumnName(gdf_hex_new, list(sc.hex_fieldNames.values()))

    if sc.hex_fieldNames["study_region"] not in gdf_hex_new.columns.to_list():
        gdf_hex_new[sc.hex_fieldNames["study_region"]] = city
    # save the gdf_hex_new to geopackage
    gdf_hex_new.to_file(gpkg_output, layer=city, driver="GPKG")
    return gdf_hex_new


def calc_hexes_zscore_walk(gpkg_output, cityNames):
    """
    Calculate zscore of hexagon-level indicators and walkability relative to all city, and save to output geopackage

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
    # field names in hex layer that are needed to calculate z scores
    fieldNames = [
        sc.hex_fieldNames["local_nh_population_density"],
        sc.hex_fieldNames["local_nh_intersection_density"],
        sc.hex_fieldNames["local_daily_living"],
    ]
    # new field names for the z score indicators
    fieldNames_new = [
        sc.hex_fieldNames["all_cities_z_nh_population_density"],
        sc.hex_fieldNames["all_cities_z_nh_intersection_density"],
        sc.hex_fieldNames["all_cities_z_daily_living"],
    ]

    fieldNames_zip = list(zip(fieldNames, fieldNames_new))
    # calculate the zscores of indicators accross cities
    for index, layer in enumerate(gdf_layers):
        for field_zip in fieldNames_zip:
            mean, std = getMeanStd(all_cities_hex_df, field_zip[0])
            layer[field_zip[1]] = (layer[field_zip[0]] - mean) / std
        # calculate the accross-city walkability index by summing all zscore indicators
        layer[sc.hex_fieldNames["all_cities_walkability"]] = layer[fieldNames_new].sum(axis=1)
        # save the indicators to out the output geopackage
        layer.to_file(gpkg_output, layer=cityNames[index], driver="GPKG")


def calc_cities_pop_pct_indicators(gpkg_hex_250m, city, gpkg_input, gpkg_output):
    """
    Calculate population-weighted city-level indicators,
    and save to output geopackage

    These indicators include:
        'pop_pct_access_500m_fresh_food_markets',
        'pop_pct_access_500m_convenience',
        'pop_pct_access_500m_pt_any',
        'pop_pct_access_500m_public_open_space',
        'pop_nh_pop_density',
        'pop_nh_intersection_density',
        'pop_daily_living',
        'pop_walkability',
        'all_cities_pop_z_daily_living',
        'all_cities_walkability'


    Parameters
    ----------
    gpkg_hex_250m: str
        file path of accross-ctiy hexagon-level indicators
    city: str
        the name of a city
    gpkg_input: str
        file path of input geopackage
    gpkg_output: str
        file path of output geopackage

    Returns
    -------
    list, list of GeoDataFrame
    """
    gdf_hex = gpd.read_file(gpkg_hex_250m, layer=city)

    gdf_hex_origin = gpd.read_file(gpkg_input, layer=sc.cities_parameters["hex250"])
    gdf_study_region = gpd.read_file(gpkg_input, layer=sc.cities_parameters["urban_study_region"])
    # join pop_est from original hex to processed hex
    gdf_hex = gdf_hex.join(gdf_hex_origin.set_index("index"), on="index", how="left", rsuffix="_origin")
    # calculate the sum of urban sample point counts for city
    gdf_study_region[sc.city_fieldNames["urban_sample_point_count"]] = gdf_hex[
        sc.hex_fieldNames["urban_sample_point_count"]
    ].sum()

    # hex-level field names from city-specific hex indicators gpkg
    fieldNames = [
"pct_access_500m_fresh_food_markets"],
"pct_access_500m_convenience"],
"pct_access_500m_pt_any"],
"pct_access_500m_public_open_space"],
"local_nh_population_density"],
"local_nh_intersection_density"],
"local_daily_living"],
"local_walkability"],
"all_cities_z_daily_living"],
"all_cities_walkability"],
    ]
    # new file names for population-weighted city-level indicators
    fieldNames_new = [
        sc.city_fieldNames["pop_pct_access_500m_fresh_food_markets"],
        sc.city_fieldNames["pop_pct_access_500m_convenience"],
        sc.city_fieldNames["pop_pct_access_500m_pt_any"],
        sc.city_fieldNames["pop_pct_access_500m_public_open_space"],
        sc.city_fieldNames["pop_nh_pop_density"],
        sc.city_fieldNames["pop_nh_intersection_density"],
        sc.city_fieldNames["pop_daily_living"],
        sc.city_fieldNames["pop_walkability"],
        sc.city_fieldNames["all_cities_pop_z_daily_living"],
        sc.city_fieldNames["all_cities_walkability"],
    ]
    # calculate the population weighted city-level indicators
    gdf_study_region = aggregation_pop_weighted(gdf_hex, gdf_study_region, list(zip(fieldNames, fieldNames_new)))

    gdf_study_region.to_file(gpkg_output, layer=city, driver="GPKG")
    return gdf_study_region


def aggregation_sp_weighted(gdf_hex, gdf_samplePoint, fieldNames):
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
        df = gdf_samplePoint[["hex_id", names[0]]].groupby("hex_id").mean()
        # join the indicator results back to hex GeoDataFrame
        gdf_hex = gdf_hex.join(df, how="left", on="index")
        # rename the fieldNames for hex-level indicators
        gdf_hex.rename(columns={names[0]: names[1]}, inplace=True)
    return gdf_hex


def aggregation_pop_weighted(input_gdf, out_gdf, fieldNames):
    """
    Aggregating hexagon level indicators to city level by weighted population

    Parameters
    ----------
    input_gdf: GeoDataFrame
        GeoDataFrame of input hexagon
    out_gdf: GeoDataFrame
        GeoDataFrame of output city
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
        out_gdf[field[1]] = (input_gdf[sc.cities_parameters["pop_est"]] * input_gdf[field[0]]).sum() / (
            input_gdf[sc.cities_parameters["pop_est"]].sum()
        )
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
    Calculate mean and sample standard deviation from the combined dataframe of all cities

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
