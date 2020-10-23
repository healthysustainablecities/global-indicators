################################################################################
# Module: setup_aggr.py
# Description: this module contains functions to set up within and across city indicators

################################################################################

import geopandas as gpd
import pandas as pd
import setup_config as sc
from tqdm import tqdm

cities_config = sc.cities_config

def calc_hexes_pct_sp_indicators(gpkg_input, gpkg_output, city, layer_samplepoint, layer_hex):
    """
    Caculate sample point weighted hexagon-level indicators within each city,
    and save to output geopackage

    Parameters
    ----------
    gpkg_input: str
        file path of sample point input geopackage
    gpkg_output: str
        file path of hex grid output geopackage
    city: str
        the name of a city
    layer_samplepoint: str
        the name of sample point layer in input geopackage
    layer_hex: str
        the name of hex layer in input geopackage

    Returns
    -------
    list, list of GeoDataFrame
    """
    # read input geopackage with processed sample point and hex layer
    gdf_samplepoint = gpd.read_file(gpkg_input, layer=layer_samplepoint)
    gdf_samplepoint = gdf_samplepoint[['hex_id']+sc.fieldNames_from_samplePoint]
    gdf_samplepoint.columns = ['hex_id']+sc.fieldNames2hex
    
    gdf_hex = gpd.read_file(gpkg_input, layer=layer_hex)
    
    # join urban sample point count for each hex to gdf_hex
    samplepoint_count = gdf_samplepoint["hex_id"].value_counts()
    samplepoint_count.name = "urban_sample_point_count"
    gdf_hex = gdf_hex.join(samplepoint_count, how="inner", on="index")
    
    # perform aggregation functions to calculate sample point weighted hex level indicators
    gdf_samplepoint = gdf_samplepoint.groupby("hex_id").mean()
    gdf_hex = gdf_hex.join(gdf_samplepoint, how="left", on="index")
    
    # scale percentages from proportions
    pct_fields = [x for x in gdf_hex if x.startswith('pct_access')]
    gdf_hex[pct_fields] = gdf_hex[pct_fields] * 100
    
    if "study_region" not in gdf_hex.columns:
        gdf_hex["study_region"] = city.title().replace('_',' ')
    
    gdf_hex = gdf_hex[[x for x in sc.hex_fieldNames if x in gdf_hex.columns]]
    # save the gdf_hex to geopackage
    gdf_hex.to_file(gpkg_output, layer=city, driver="GPKG")


def calc_hexes_zscore_walk(gpkg_output_hex, cities):
    """
    Calculate zscore of hexagon-level indicators and walkability relative to all city, and save to output geopackage

    These indicators include (z-score of population weighted indicators relative to all cities):
        "all_cities_z_nh_population_density",
        "all_cities_z_nh_intersection_density",
        "all_cities_z_daily_living",
        "all_cities_walkability"

    Parameters
    ----------
    gpkg_output_hex: str
        file path of output geopackage
    cities: list
        all the city names

    Returns
    -------
    none
    """
    print("  - read and append all cities hex layer from the output geopackage")
    gdf_layers = []
    for i in tqdm(cities):
        try:
            gdf = gpd.read_file(gpkg_output_hex, layer=i)
            gdf = gdf.reindex(columns=sorted(gdf.columns))
            gdf_layers.append(gdf)
        except ValueError as e:
            print(e)

    # concatenate all cities hex layers into one a dataframe
    all_cities_hex_df = pd.concat(gdf_layers, ignore_index=True)
    # zip field names in hex layer that are needed to calculate z scores with new field names for the z score indicators
    fieldNames_hex = [sc.field_lookup[x]['hex'] for x in sc.field_lookup if '_z_' in sc.field_lookup[x]['all']]
    fieldNames_new = [sc.field_lookup[x]['all'] for x in sc.field_lookup if '_z_' in sc.field_lookup[x]['all']]
    # calculate the zscores of indicators accross cities
    for index, layer in enumerate(tqdm(gdf_layers)):
        for old,new in list(zip(fieldNames_hex,fieldNames_new)):
            mean = all_cities_hex_df[old].mean()
            std = all_cities_hex_df[old].std()
            layer[new] = (layer[old] - mean) / std
        # calculate the accross-city walkability index by summing all zscore indicators
        layer["all_cities_walkability"] = layer[fieldNames_new].sum(axis=1)
        # save the indicators to out the output geopackage
        field_order = sc.hex_fieldNames + [x for x in layer.columns if x not in sc.hex_fieldNames]
        layer[field_order].to_file(gpkg_output_hex, layer=cities[index], driver="GPKG")

def calc_cities_pop_pct_indicators(gpkg_output_hex, city, gpkg_input, gpkg_output_cities,extra_unweighted_vars = []):
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
    gpkg_output_hex: str
        file path of accross-ctiy hexagon-level indicators
    city: str
        the name of a city
    gpkg_input: str
        file path of input geopackage
    gpkg_output_cities: str
        file path of output geopackage
    extra_unweighted_vars: list
        an optional list of variables to also calculate mean (unweighted) for
    
    Returns
    -------
    list, list of GeoDataFrame
    """
    gdf_hex = gpd.read_file(gpkg_output_hex, layer=city)

    gdf_hex_origin = gpd.read_file(gpkg_input, layer=sc.cities_parameters["hex250"])
    gdf_study_region = gpd.read_file(gpkg_input, layer=sc.cities_parameters["urban_study_region"])
    urban_covariates = gpd.read_file(gpkg_input, layer="urban_covariates")
    # join pop_est from original hex to processed hex
    gdf_hex = gdf_hex.join(gdf_hex_origin.set_index("index"), on="index", how="left", rsuffix="_origin")
    # calculate the sum of urban sample point counts for city
    urban_covariates['urban_sample_point_count'] = gdf_hex["urban_sample_point_count"].sum()
    urban_covariates['geometry'] = gdf_study_region["geometry"]
    
    # hex-level field names from city-specific hex indicators gpkg
    fieldNames = [x for x in sc.hex_fieldNames if x not in sc.basic_attributes]
    
    # new file names for population-weighted city-level indicators
    fieldNames_new = [x for x in sc.city_fieldNames if x not in sc.basic_attributes]
    
    # calculate the population weighted city-level indicators
    for i,o in zip(fieldNames,fieldNames_new):
        # calculate the population weighted indicators based on input hexagon layer
        # sum to aggregate up to the city level
        urban_covariates[o] = (gdf_hex[sc.cities_parameters["pop_est"]] * gdf_hex[i]).sum() / (
            gdf_hex[sc.cities_parameters["pop_est"]].sum()
        )
    # append any requested unweighted indicator averages
    urban_covariates = urban_covariates.join(pd.DataFrame(gdf_hex[extra_unweighted_vars].mean()).transpose())
    # order geometry as final column
    urban_covariates.columns = [x for x in urban_covariates.columns if x!='geometry']+['geometry']
    urban_covariates.to_file(gpkg_output_cities, layer=city, driver="GPKG")
    # transform to WGS84 EPSG 4326, for combined all cities layer
    urban_covariates.to_epsg(4326)
    return urban_covariates
