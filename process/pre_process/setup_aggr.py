################################################################################
# Module: setup_aggr.py
# Description: this module contains functions to set up within and across city indicators

################################################################################

import geopandas as gpd
import pandas as pd
import numpy as np

def calc_grid_pct_sp_indicators(region_dictionary,indicators):
    """
    Caculate sample point weighted grid-level indicators within each city,
    and save to output geopackage

    Parameters
    ----------
    region_dictionary: dict
        gpkg: path of geopackage file with city resources for inputs and outputs
        city_name: city full name
        grid_summary_output: output name for CSV file and gpkg layer summarising grid results
                     e.g. {study_region}_grid_{resolution}m_yyyymmdd
        city_summary_output: output name for CSV file and gpkg layer summarising city results
                      {study_region}_city_yyyymmdd
    indicators: dict
        output: dict
            sample_point_variables: list
            neighbourhood_variables: list
        
    Returns
    -------
    String (indicating presumptive success)
    """
    gpkg = region_dictionary['gpkg']
    # read input geopackage with processed sample point and grid layer
    gdf_samplepoint = gpd.read_file(gpkg, layer="samplePointsData")
    gdf_samplepoint = gdf_samplepoint[['grid_id']+indicators['output']['sample_point_variables']]
    gdf_samplepoint.columns = ['grid_id']+indicators['output']['neighbourhood_variables']
    
    gdf_grid = gpd.read_file(gpkg, layer=region_dictionary['population_grid'])
    
    # join urban sample point count to gdf_grid
    samplepoint_count = gdf_samplepoint["grid_id"].value_counts()
    samplepoint_count.name = "urban_sample_point_count"
    gdf_grid = gdf_grid.join(samplepoint_count, how="inner", on="grid_id")
    
    # perform aggregation functions to calculate sample point weighted grid cell indicators
    # to retain indicators which may be all NaN (eg cities absent GTFS data), numeric_only=False
    gdf_samplepoint = gdf_samplepoint\
        .groupby("grid_id")\
        .mean(numeric_only=False)
    gdf_grid = gdf_grid.join(gdf_samplepoint, how="left", on="grid_id")
    
    # scale percentages from proportions
    pct_fields = [x for x in gdf_grid if x.startswith('pct_access')]
    gdf_grid[pct_fields] = gdf_grid[pct_fields] * 100
    
    gdf_grid["study_region"] = region_dictionary['full_locale']
    
    grid_fields = indicators['output']['basic_attributes']+indicators['output']['neighbourhood_variables']
    grid_fields = [x for x in grid_fields if x in gdf_grid.columns]
    
    # save the gdf_grid to geopackage
    gdf_grid[grid_fields+['geometry']].to_file(
        gpkg, 
        layer=region_dictionary['grid_summary'], 
        driver="GPKG"
        )
    gdf_grid[grid_fields]\
        .to_csv(f"{region_dictionary['locale_dir']}/{region_dictionary['grid_summary']}.csv",
        index=False)
    return "Exported gridded small area summary statistics"

def calc_cities_pop_pct_indicators(region_dictionary, indicators):
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
        'pop_walkability'

    Parameters
    ----------
    region_dictionary: dict
        gpkg: path of geopackage file with city resources for inputs and outputs
        city_name: city full name
        grid_summary_output: output name for CSV file and gpkg layer summarising grid results
                     e.g. {study_region}_grid_{resolution}m_yyyymmdd
        city_summary_output: output name for CSV file and gpkg layer summarising city results
                      {study_region}_city_yyyymmdd
    indicators: dict
        output: dict
            sample_point_variables: list
            neighbourhood_variables: list
            extra_unweighted_vars: list
                an optional list of variables to also calculate mean (unweighted) for
    
    Returns
    -------
    String (indicating presumptive success)
    """
    gpkg = region_dictionary['gpkg']
    gdf_grid = gpd.read_file(gpkg, layer=region_dictionary['grid_summary'])
    
    gdf_grid_origin = gpd.read_file(gpkg, layer=region_dictionary['population_grid'])
    gdf_study_region = gpd.read_file(gpkg, layer="urban_study_region")
    urban_covariates = gpd.read_file(gpkg, layer="urban_covariates")
    # join pop_est from original grid to processed grid
    gdf_grid = gdf_grid.join(gdf_grid_origin.set_index("grid_id"), on="grid_id", how="left", rsuffix="_origin")
    # calculate the sum of urban sample point counts for city
    urban_covariates['urban_sample_point_count'] = gdf_grid["urban_sample_point_count"].sum()
    urban_covariates['geometry'] = gdf_study_region["geometry"]
    urban_covariates.crs = gdf_study_region.crs
    
    # Map differences in grid names to city names
    # (implies weighting when aggregating)
    name_mapping = [z for z in zip(
        indicators['output']['neighbourhood_variables'][1:], 
        indicators['output']['city_variables']
        ) if z[0]!=z[1]]
    
    # calculate the population weighted city-level indicators
    N = gdf_grid["pop_est"].sum()
    for i,o in name_mapping:
        # If all entries of field in gdf_grid are null, results should be returned as null
        if gdf_grid[i].isnull().all():
            urban_covariates[o] = np.nan
        else:
            # calculate the city level population weighted indicator estimate
            urban_covariates[o] = (
                gdf_grid["pop_est"] * gdf_grid[i]
                ).sum()/N
    
    # append any requested unweighted indicator averages
    urban_covariates = urban_covariates.join(
        pd.DataFrame(
            gdf_grid[indicators['output']['extra_unweighted_vars']].mean()
            ).transpose()
        )
    # order geometry as final column
    urban_covariates = urban_covariates[
        [x for x in urban_covariates.columns if x!='geometry']+['geometry']
        ]
    urban_covariates.to_file(
        gpkg,
        layer=region_dictionary['city_summary'], 
        driver="GPKG"
        )
    urban_covariates[[x for x in urban_covariates.columns if x!='geometry']]\
        .to_csv(f"{region_dictionary['locale_dir']}/{region_dictionary['city_summary']}.csv",
        index=False)

