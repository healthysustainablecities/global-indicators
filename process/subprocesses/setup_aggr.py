"""
Set up aggregation functions.

This module contains functions to set up indicators for within- and between- city comparisons.
"""

import geopandas as gpd
import numpy as np
import pandas as pd


def calc_grid_pct_sp_indicators(engine, region_config, indicators):
    """Caculate sample point weighted grid-level indicators within each city.

    Parameters
    ----------
    engine: sql connection
    region_config: dict
        city_name: city full name
        grid_summary_output: output name for CSV file and db layer summarising grid results
                     e.g. {study_region}_grid_{resolution}m
        city_summary_output: output name for CSV file and db layer summarising city results
                      {study_region}_city
    indicators: dict
        output: dict
            sample_point_variables: list
            neighbourhood_variables: list

    Returns
    -------
    String (indicating presumptive success)
    """
    # read sample point and grid layer
    with engine.connect() as connection:
        gdf_grid = gpd.read_postgis(
            region_config['population_grid'], connection, index_col='grid_id',
        )
    with engine.connect() as connection:
        gdf_sample_points = gpd.read_postgis(
            region_config['point_summary'], connection, index_col='point_id',
        )
    gdf_sample_points = gdf_sample_points[
        ['grid_id'] + indicators['output']['sample_point_variables']
    ]
    gdf_sample_points.columns = ['grid_id'] + indicators['output'][
        'neighbourhood_variables'
    ]

    # join urban sample point count to gdf_grid
    sample_points_count = gdf_sample_points['grid_id'].value_counts()
    sample_points_count.name = 'urban_sample_point_count'
    gdf_grid = gdf_grid.join(sample_points_count, how='inner', on='grid_id')

    # perform aggregation functions to calculate sample point weighted grid cell indicators
    # to retain indicators which may be all NaN (eg cities absent GTFS data), numeric_only=False
    gdf_sample_points = gdf_sample_points.groupby('grid_id').mean(
        numeric_only=False,
    )
    gdf_grid = gdf_grid.join(gdf_sample_points, how='left', on='grid_id')

    # scale percentages from proportions
    pct_fields = [x for x in gdf_grid if x.startswith('pct_access')]
    gdf_grid[pct_fields] = gdf_grid[pct_fields] * 100

    gdf_grid['study_region'] = region_config['name']

    grid_fields = (
        indicators['output']['basic_attributes']
        + indicators['output']['neighbourhood_variables']
    )
    grid_fields = [x for x in grid_fields if x in gdf_grid.columns]

    # save the grid indicators
    with engine.connect() as connection:
        gdf_grid[grid_fields + ['geom']].set_geometry('geom').to_postgis(
            region_config['grid_summary'],
            connection,
            index=True,
            if_exists='replace',
        )
    gdf_grid[grid_fields].to_csv(
        f"{region_config['region_dir']}/{region_config['grid_summary']}.csv",
        index=False,
    )
    return 'Exported gridded small area summary statistics'


def calc_cities_pop_pct_indicators(engine, region_config, indicators):
    """Calculate population-weighted city-level indicators.

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
    engine: sql connection
    region_config: dict
        city_name: city full name
        grid_summary_output: output name for CSV file and db layer summarising grid results
             e.g. {study_region}_grid_{resolution}m
        city_summary_output: output name for CSV file and db layer summarising city results
                  {study_region}_city
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
    with engine.connect() as connection:
        gdf_grid = gpd.read_postgis(
            region_config['grid_summary'], connection, index_col='grid_id',
        )
    with engine.connect() as connection:
        gdf_study_region = gpd.read_postgis('urban_study_region', connection)
    with engine.connect() as connection:
        urban_covariates = pd.read_sql_table('urban_covariates', connection)
    # calculate the sum of urban sample point counts for city
    urban_covariates['urban_sample_point_count'] = gdf_grid[
        'urban_sample_point_count'
    ].sum()
    urban_covariates['geom'] = gdf_study_region['geom']
    urban_covariates.crs = gdf_study_region.crs

    # Map differences in grid names to city names
    # (implies weighting when aggregating)
    name_mapping = [
        z
        for z in zip(
            indicators['output']['neighbourhood_variables'],
            indicators['output']['city_variables'],
        )
        if z[0] != z[1]
    ]

    # calculate the population weighted city-level indicators
    N = gdf_grid['pop_est'].sum()
    for i, o in name_mapping:
        # If all entries of field in gdf_grid are null, results should be returned as null
        if gdf_grid[i].isnull().all():
            urban_covariates[o] = np.nan
        else:
            # calculate the city level population weighted indicator estimate
            urban_covariates[o] = (gdf_grid['pop_est'] * gdf_grid[i]).sum() / N

    # append any requested unweighted indicator averages
    urban_covariates = urban_covariates.join(
        pd.DataFrame(
            gdf_grid[indicators['output']['extra_unweighted_vars']].mean(),
        ).transpose(),
    )
    # order geometry as final column
    urban_covariates = urban_covariates[
        [x for x in urban_covariates.columns if x != 'geom'] + ['geom']
    ]
    urban_covariates = urban_covariates.set_geometry('geom')
    with engine.connect() as connection:
        urban_covariates.to_postgis(
            region_config['city_summary'], connection, if_exists='replace',
        )
    urban_covariates[
        [x for x in urban_covariates.columns if x != 'geom']
    ].to_csv(
        f"{region_config['region_dir']}/{region_config['city_summary']}.csv",
        index=False,
    )
