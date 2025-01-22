"""
Aggregation.

Aggregate sample point indicators for population grid and overall study region summaries.
"""

import subprocess as sp
import sys
import time

# Set up project and region parameters for GHSCIC analyses
import geopandas as gpd
import ghsci
import numpy as np
import pandas as pd
from geoalchemy2 import Geometry
from script_running_log import script_running_log
from sqlalchemy import text


def calc_grid_pct_sp_indicators(r: ghsci.Region, indicators: dict) -> None:
    """Caculate sample point weighted grid-level indicators within each city.

    Parameters
    ----------
    r: ghsci.Region
    indicators: dict
        output: dict
            sample_point_variables: list
            neighbourhood_variables: list

    Returns
    -------
    String (indicating presumptive success)
    """
    # read sample point and grid layer
    with r.engine.connect() as connection:
        gdf_grid = gpd.read_postgis(
            r.config['population_grid'], connection, index_col='grid_id',
        )
    with r.engine.connect() as connection:
        gdf_sample_points = gpd.read_postgis(
            r.config['point_summary'], connection, index_col='point_id',
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

    gdf_grid['study_region'] = r.config['name']

    grid_fields = (
        indicators['output']['basic_attributes']
        + indicators['output']['neighbourhood_variables']
    )
    grid_fields = [x for x in grid_fields if x in gdf_grid.columns]

    # save the grid indicators
    with r.engine.connect() as connection:
        gdf_grid[grid_fields + ['geom']].set_geometry('geom').to_postgis(
            r.config['grid_summary'],
            connection,
            index=True,
            if_exists='replace',
        )
    # gdf_grid[grid_fields].to_csv(
    #     f"{r.config['region_dir']}/{r.codename}_{r.config['grid_summary']}.csv",
    #     index=False,
    # )


def calc_cities_pop_pct_indicators(r: ghsci.Region, indicators: dict) -> None:
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
    r: ghsci.Region
    indicators: dict

    Returns
    -------
    String (indicating presumptive success)
    """
    gdf_grid = r.get_gdf(r.config['grid_summary'], index_col='grid_id')
    gdf_study_region = r.get_gdf('urban_study_region')
    urban_covariates = r.get_df('urban_covariates')
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
    with r.engine.connect() as connection:
        urban_covariates.to_postgis(
            r.config['city_summary'], connection, if_exists='replace',
        )
    # urban_covariates[
    #     [x for x in urban_covariates.columns if x != 'geom']
    # ].to_csv(
    #     f"{r.config['region_dir']}/{r.codename}_{r.config['city_summary']}.csv",
    #     index=False,
    # )


def custom_data_load(r: ghsci.Region, agg) -> str:
    try:
        boundary_data = r.config['custom_aggregations'][agg]['data']
        table = f'agg_{agg}'
        if '.gpkg:' in boundary_data:
            gpkg = boundary_data.split(':')
            boundary_data = gpkg[0]
            query = gpkg[1]
        else:
            query = ''
        command = (
            '            ogr2ogr -overwrite -progress -f "PostgreSQL" '
            f' PG:"host={r.config["db_host"]} port={r.config["db_port"]} dbname={r.config["db"]}'
            f' user={r.config["db_user"]} password={r.config["db_pwd"]}" '
            f' "/home/ghsci/process/data/{boundary_data}" '
            f' -lco geometry_name="geom" -lco precision=NO '
            f' -t_srs {r.config["crs_srid"]} -nln "{table}" '
            f' -nlt PROMOTE_TO_MULTI'
            f' {query}'
        )
        print(command)
        failure = sp.call(command, shell=True)
        if failure == 1:
            sys.exit(
                f"Error when attempting to aggregate for {agg} '{boundary_data}' (check custom aggregation configuration).",
            )
        return table
    except Exception as e:
        sys.exit(
            f"Error when attempting to aggregate for {agg} '{boundary_data}' (check custom aggregation configuration): {e}",
        )


def custom_aggregation(r: ghsci.Region, indicators: dict) -> None:
    """Aggregate indicators for custom areas."""
    processed_aggs = []
    for agg in r.config['custom_aggregations']:
        table = f'indicators_{agg}'
        keep_columns = r.config['custom_aggregations'][agg].pop(
            'keep_columns', '',
        )
        if keep_columns != '':
            keep_columns = f'{keep_columns},'
        print(f'\n  - {table}')
        boundary_data = r.config['custom_aggregations'][agg]['data']
        if boundary_data.startswith('OSM:'):
            boundaries = f'{r.config["osm_prefix"]}_polygon'
            id = 'osm_id'
            query = f"WHERE {boundary_data.split(':')[1].strip()}".replace(
                'WHERE *', '',
            )
        else:
            boundaries = custom_data_load(r, agg)
            id = r.config['custom_aggregations'][agg].pop('id', 'ogc_fid')
            query = ''
        agg_source = r.config['custom_aggregations'][agg].pop(
            'aggregation_source', None,
        )
        if agg_source is None:
            print('    No aggregation source specified, skipping.')
            continue
        else:
            if agg_source in ['point', 'grid']:
                if agg_source == 'point':
                    count_units = 'sample_point_count'
                    indicator_list = indicators['output'][
                        'sample_point_variables'
                    ]
                else:
                    count_units = 'grid_count'
                    indicator_list = indicators['output'][
                        'neighbourhood_variables'
                    ]
                agg_source = r.config[f'{agg_source}_summary']
            elif agg_source in processed_aggs:
                # unclear if this will always be appropriate; may need customisation
                indicator_list = indicators['output'][
                    'neighbourhood_variables'
                ]
            else:
                print(
                    f'    Aggregating source {agg_source} could not be identified; skipping.',
                )
                continue
        agg_distance = r.config['custom_aggregations'][agg].pop(
            'aggregate_within_distance', None,
        )
        if agg_distance is not None:
            agg_on = f"""ST_DWithin(b.geom, s.geom, {int(agg_distance)})"""
        else:
            agg_on = """ST_Intersects(b.geom, s.geom)"""
        weight = r.config['custom_aggregations'][agg].pop('weight', None)
        if agg_source == r.config['grid_summary'] and weight not in [
            None,
            'false',
            False,
        ]:
            # using population weighting
            # if there are zero weights the indicator is null
            # else, calculate the value of the weighted indicator
            weighting = '''
                (CASE
                    WHEN COALESCE(SUM(s."{weight}"),0) = 0
                        THEN NULL
                    ELSE
                        (SUM(s."{weight}"*s."{i}"::numeric)/SUM(s."{weight}"))::numeric
                END) AS "{weight}_{i}"
                '''
            agg_formula = ','.join(
                [weighting.format(i=i, weight=weight) for i in indicator_list],
            )
        else:
            agg_formula = ','.join(
                [
                    f'''AVG(s."{i}"::numeric) AS "avg_{i}"'''
                    for i in indicator_list
                ],
            )
        queries = [
            f"""DROP TABLE IF EXISTS {table};""",
            f"""CREATE TABLE "{table}" AS
            SELECT b.{id},
            {keep_columns}
            ST_Area(b.geom)/10^6 AS area_sqkm,
            COUNT(s.*) AS {count_units},
            {agg_formula},
            b.geom
            FROM "{boundaries}" b
            LEFT JOIN "{agg_source}" s ON {agg_on}
            {query}
            GROUP BY b.{id}, {keep_columns} b.geom;""",
            f"""DELETE FROM {table} WHERE {count_units} = 0;""",
            f"""CREATE INDEX {table}_ix  ON {table} ({id});""",
            f"""CREATE INDEX {table}_gix ON {table} USING GIST(geom);""",
        ]
        for query in queries:
            try:
                print(query)
                with r.engine.begin() as connection:
                    connection.execute(text(query))
                processed_aggs.append(agg)
            except Exception as e:
                sys.exit(
                    f"Error when attempting to aggregate for {agg} '{boundary_data}' (check custom aggregation configuration): {e}",
                )


def aggregate_study_region_indicators(codename):
    start = time.time()
    script = '_13_aggregation'
    task = 'Compile study region destinations'
    r = ghsci.Region(codename)
    print('\nCalculating small area neighbourhood grid indicators... ')
    # calculate within-city indicators weighted by sample points for each city
    # calc_grid_pct_sp_indicators take sample point stats within each city as
    # input and aggregate up to grid cell indicators by calculating the mean of
    # sample points stats within each hex
    calc_grid_pct_sp_indicators(r, ghsci.indicators)

    print('\nCalculating city summary indicators... ')
    # Calculate city-level indicators weighted by population
    # calc_cities_pop_pct_indicators function take grid cell indicators and
    # pop estimates of each city as input then aggregate grid cell to city-level
    # indicator by summing all the population weighted grid cell indicators

    # in addition to the population weighted averages, unweighted averages are
    # also included to reflect the spatial distribution of key walkability
    # measures (regardless of population distribution)
    calc_cities_pop_pct_indicators(r, ghsci.indicators)

    print('\nCalculating custom aggregation indicators... ')
    custom_aggregation(r, ghsci.indicators)

    # output to completion log
    script_running_log(r.config, script, task, start)
    r.engine.dispose()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    aggregate_study_region_indicators(codename)


if __name__ == '__main__':
    main()
