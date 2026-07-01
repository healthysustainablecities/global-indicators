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
    gdf_grid = r.get_gdf(
        f"""
        SELECT p.*
        FROM {r.config['population_grid']} p,
                urban_study_region u
        WHERE ST_Intersects(p.geom, u.geom)
        AND (ST_Area(ST_Intersection(p.geom, u.geom)) / ST_Area(p.geom)) >= 0.1
        """,
    )
    gdf_sample_points = r.get_gdf(r.config['point_summary'])
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
    gdf_grid = r.get_gdf(r.config['grid_summary'])
    gdf_study_region = r.get_gdf('urban_study_region')
    urban_covariates = r.get_df('urban_covariates')
    custom_population = r.config['population'].get('custom_population')
    if custom_population and custom_population in r.config.get(
        'custom_aggregations',
        {},
    ):
        with r.engine.connect() as connection:
            urban_covariates['urban_sample_point_count'] = connection.execute(
                text('SELECT count(*) FROM urban_sample_points'),
            ).scalar()
    else:
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
            r.config['city_summary'],
            connection,
            if_exists='replace',
        )


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
    name_mapping = {
        z[0]: z[1]
        for z in zip(
            indicators['output']['sample_point_variables'],
            indicators['output']['neighbourhood_variables'],
        )
        if z[0] != z[1]
    }
    for agg in r.config['custom_aggregations']:
        table = f'indicators_{agg}'
        keep_columns = r.config['custom_aggregations'][agg].pop(
            'keep_columns',
            '',
        )
        if keep_columns != '':
            keep_columns = f'{keep_columns},'
        print(f'\n  - {table}')
        boundary_data = r.config['custom_aggregations'][agg]['data']
        if boundary_data.startswith('OSM:'):
            boundaries = f'{r.config["osm_prefix"]}_polygon'
            id = 'osm_id'
            query = f"WHERE {boundary_data.split(':')[1].strip()}".replace(
                'WHERE *',
                '',
            )
        else:
            boundaries = custom_data_load(r, agg)
            id = r.config['custom_aggregations'][agg].pop('id', 'ogc_fid')
            if id is None:
                id = 'ogc_fid'
            query = ''
        agg_source = r.config['custom_aggregations'][agg].pop(
            'aggregation_source',
            None,
        )
        if agg_source is None:
            print('    No aggregation source specified, skipping.')
            continue
        else:
            if agg_source in ['point', 'grid']:
                if agg_source == 'point':
                    count_units = 'urban_sample_point_count'
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
            'aggregate_within_distance',
            None,
        )
        if agg_distance is not None:
            agg_on = f"""ST_DWithin(b.geom, s.geom, {int(agg_distance)})"""
        else:
            agg_on = """ST_Intersects(b.geom, s.geom)"""
        weight = r.config['custom_aggregations'][agg].pop('weight', None)
        agg_weight = f"""COALESCE(SUM({weight}),0)"""
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
                        (SUM(s."{weight}"*s."{i}"::float8)/SUM(s."{weight}"))::float8
                END) AS "{weight}_{i}"
                '''
            agg_formula = ','.join(
                [weighting.format(i=i, weight=weight) for i in indicator_list],
            )
        else:
            agg_formula = ','.join(
                [
                    f'''\n    {100.0 if name_mapping.get(i, '').startswith('pct') else 1.0} * AVG(s."{i}"::float8) AS "{name_mapping.get(i, "avg_" + i)}"'''
                    for i in indicator_list
                ],
            )
        queries = [
            f"""DROP TABLE IF EXISTS {table};""",
            f"""CREATE TABLE "{table}" AS
    SELECT b.{id},
    {keep_columns}
    ST_Area(b.geom)/10^6 AS area_sqkm,
    {agg_weight if weight else 'NULL'} AS pop_est,
    {f'{agg_weight}/ST_Area(b.geom)/10^6' if weight else 'NULL'} AS pop_per_sqkm,
    COUNT(i.*) AS intersection_count,
    COUNT(i.*)/ST_Area(b.geom)/10^6 AS intersections_per_sqkm,
    COUNT(s.*) AS {count_units},
    {agg_formula},
    b.geom
    FROM "{boundaries}" b
    LEFT JOIN "{agg_source}" s ON {agg_on}
    LEFT JOIN "{r.config['intersections_table']}" i ON ST_Intersects(s.geom, i.geom)
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


def calc_cycling_indicators(r: ghsci.Region) -> None:
    """Aggregate cycling sample-point indicators to the grid and city summaries.

    Gated by the region's cycling_indicators config.  Adds (does not replace) columns
    to the existing grid and city summary tables: per grid-cell mean access (as a
    percentage) and mean safe-route distance, plus the population-weighted city values.
    """
    from _cycling_lts_network import cycling_config

    if cycling_config(r) is None or 'sample_points_cycling' not in r.get_tables():
        return

    cols = r.get_df(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'sample_points_cycling'",
    )['column_name'].tolist()
    # two measures are aggregated: the strict low-stress headline (sp_cycle_safe_access_* /
    # sp_cycle_safe_nearest_node_*) and the danger-weighted secondary (sp_cycle_access_* /
    # sp_cycle_nearest_node_*).  Prefix mapping (check the more specific 'safe' form first):
    prefix_map = [
        ('sp_cycle_safe_access_', 'pct_access_cycle_safe_', True),
        ('sp_cycle_access_', 'pct_access_cycle_', True),
        ('sp_cycle_safe_nearest_node_', 'avg_cycle_dist_safe_', False),
        ('sp_cycle_nearest_node_', 'avg_cycle_dist_', False),
    ]

    def _classify(col):
        for src, dest, is_access in prefix_map:
            if col.startswith(src):
                return dest + col[len(src):], is_access
        return None, None

    rename, access_cols, value_cols = {}, [], []
    for c in cols:
        new, is_access = _classify(c)
        if new is None:
            continue
        rename[c] = new
        value_cols.append(c)
        if is_access:
            access_cols.append(c)
    if 'grid_id' not in cols or not value_cols:
        return

    # grid-cell means: access proportions -> percentages, distances kept in metres
    sp = r.get_df(
        f'SELECT grid_id, {", ".join(value_cols)} FROM sample_points_cycling',
    )
    grid = sp.groupby('grid_id')[value_cols].mean()
    for c in access_cols:
        grid[c] = grid[c] * 100
    grid = grid.rename(columns=rename).reset_index()
    grid_value_cols = [rename[c] for c in value_cols]

    grid_summary = r.config['grid_summary']
    grid.to_sql('_cycling_grid', r.engine, if_exists='replace', index=False)
    with r.engine.begin() as conn:
        for col in grid_value_cols:
            conn.execute(text(
                f'ALTER TABLE {grid_summary} ADD COLUMN IF NOT EXISTS '
                f'"{col}" double precision',
            ))
        set_clause = ', '.join(f'"{col}" = t."{col}"' for col in grid_value_cols)
        conn.execute(text(
            f'UPDATE {grid_summary} g SET {set_clause} '
            f'FROM _cycling_grid t WHERE g.grid_id = t.grid_id',
        ))
        conn.execute(text('DROP TABLE IF EXISTS _cycling_grid'))

    # population-weighted city-level estimates (skipping cells with no value)
    gdf_grid = r.get_df(
        f'SELECT pop_est, '
        f'{", ".join(chr(34) + c + chr(34) for c in grid_value_cols)} '
        f'FROM {grid_summary}',
    )
    city = {}
    for col in grid_value_cols:
        mask = gdf_grid[col].notna()
        w = gdf_grid.loc[mask, 'pop_est']
        city['pop_' + col] = (
            float((w * gdf_grid.loc[mask, col]).sum() / w.sum())
            if w.sum() > 0
            else None
        )

    city_summary = r.config['city_summary']
    with r.engine.begin() as conn:
        for col in city:
            conn.execute(text(
                f'ALTER TABLE {city_summary} ADD COLUMN IF NOT EXISTS '
                f'"{col}" double precision',
            ))
        assignments = ', '.join(
            f'"{col}" = ' + ('NULL' if val is None else repr(float(val)))
            for col, val in city.items()
        )
        conn.execute(text(f'UPDATE {city_summary} SET {assignments}'))
    print(
        f'  - cycling: aggregated {len(grid_value_cols)} indicators to the '
        'grid and city summaries',
    )


def aggregate_study_region_indicators(codename):
    start = time.time()
    script = '_12_aggregation'
    task = 'Compile study region destinations'
    r = ghsci.Region(codename)
    print('\nCalculating small area neighbourhood grid indicators... ')
    # calculate within-city indicators weighted by sample points for each city
    # calc_grid_pct_sp_indicators take sample point stats within each city as
    # input and aggregate up to grid cell indicators by calculating the mean of
    # sample points stats within each hex
    calc_grid_pct_sp_indicators(r, ghsci.indicators)

    print('\nCalculating custom aggregation indicators... ')
    custom_aggregation(r, ghsci.indicators)

    print('\nCalculating city summary indicators... ')
    # Calculate city-level indicators weighted by population
    # calc_cities_pop_pct_indicators function take grid cell indicators and
    # pop estimates of each city as input then aggregate grid cell to city-level
    # indicator by summing all the population weighted grid cell indicators

    # in addition to the population weighted averages, unweighted averages are
    # also included to reflect the spatial distribution of key walkability
    # measures (regardless of population distribution)
    calc_cities_pop_pct_indicators(r, ghsci.indicators)

    print('\nAggregating cycling indicators (if enabled)... ')
    calc_cycling_indicators(r)

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
