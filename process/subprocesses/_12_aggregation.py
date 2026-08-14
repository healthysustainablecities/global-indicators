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
    # Select grid cells that are at least 10% within the urban study region.
    # The region is a single, very complex MultiPolygon, so testing every grid
    # cell against it whole is pathologically slow for large cities (~30 min for
    # Melbourne).  ST_Subdivide splits it into small, individually indexable
    # pieces; because those pieces tile the polygon with no overlapping
    # interiors, summing the per-piece intersection areas is exact, so this
    # returns the identical set of cells as the naive query, but in seconds.
    gdf_grid = r.get_gdf(
        f"""
        WITH region AS (
            SELECT ST_Subdivide(ST_MakeValid(geom), 128) AS geom
            FROM urban_study_region
        ),
        member AS (
            SELECT p.grid_id
            FROM {r.config['population_grid']} p
            JOIN region r ON ST_Intersects(p.geom, r.geom)
            GROUP BY p.grid_id
            HAVING SUM(ST_Area(ST_Intersection(p.geom, r.geom)))
                   / MIN(ST_Area(p.geom)) >= 0.1
        )
        SELECT p.*
        FROM {r.config['population_grid']} p
        JOIN member m USING (grid_id)
        """,
    )
    # Only grid_id + indicator columns are needed here (point geometry is never
    # used), so read via the fast get_df path rather than parsing WKB for every
    # sample point.  get_df returns pyarrow-backed columns; cast back to numpy so
    # the grid_id join key and indicator values match the grid frame above.
    sample_point_columns = ['grid_id'] + indicators['output'][
        'sample_point_variables'
    ]
    gdf_sample_points = r.get_df(
        f'SELECT {", ".join(sample_point_columns)} '
        f'FROM {r.config["point_summary"]}',
    )
    gdf_sample_points[indicators['output']['sample_point_variables']] = (
        gdf_sample_points[
            indicators['output']['sample_point_variables']
        ].astype('float64')
    )
    gdf_sample_points['grid_id'] = gdf_sample_points['grid_id'].astype('int64')
    gdf_sample_points.columns = ['grid_id'] + indicators['output'][
        'neighbourhood_variables'
    ]
    # Sample points lacking a population grid association (possible where
    # sampling of areas lacking population data coverage has been configured)
    # are excluded from population grid and city summaries; they remain
    # included in any custom aggregations, which are spatially joined with
    # sample points directly.
    gdf_sample_points = gdf_sample_points[
        ~gdf_sample_points['grid_id'].isna()
    ].copy()
    gdf_sample_points['grid_id'] = gdf_sample_points['grid_id'].astype(int)

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
    # any 'pct_' prefixed neighbourhood variable is derived from sample point
    # proportions, not only the 'pct_access_' accessibility measures; new
    # indicators following this convention are therefore scaled consistently
    pct_fields = [x for x in gdf_grid if x.startswith('pct_')]
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
        sql_agg = agg.replace(' ', '_').lower()
        table = f'agg_{sql_agg}'
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
            f' -nlt PROMOTE_TO_MULTI -makevalid'
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


def table_columns(r: ghsci.Region, table: str) -> dict:
    """Return a table's column names, keyed by their lower case form."""
    try:
        columns = r.get_df(
            'SELECT column_name FROM information_schema.columns '
            "WHERE table_schema = 'public' "
            f"AND table_name = '{table.lower()}'",
        )['column_name'].tolist()
    except Exception:
        return {}
    return {str(c).lower(): str(c) for c in columns}


def resolve_weight(r: ghsci.Region, weight, boundaries, agg_source, agg_kind):
    """
    Locate a configured weight variable and decide how it should be applied.

    A weight may describe either the aggregation source or the boundaries
    being summarised.  Where the source is areal --- the population grid, or
    an earlier custom aggregation --- summing its weight across the units
    falling within each boundary gives that boundary's total, and indicator
    estimates can be weighted by it.  Where the source is sample points, the
    weight instead belongs to the boundary itself: sample points are equal
    probability samples of the network, so summing a boundary attribute once
    per point would multiply it by the number of points, and weighting
    indicators by a value that is constant within each boundary would have no
    effect in any case.

    Returns (expression, weighted), where expression is SQL evaluating to the
    boundary's weight total (or None if no usable weight was found), and
    weighted indicates whether indicator estimates may be weighted by it.

    Configured names are matched case insensitively, because column names are
    lower cased when boundary data is imported.
    """
    if weight in [None, 'false', False, 'False']:
        return None, False
    source_columns = table_columns(r, agg_source)
    boundary_columns = table_columns(r, boundaries)
    in_source = source_columns.get(str(weight).lower())
    in_boundary = boundary_columns.get(str(weight).lower())
    if agg_kind != 'point' and in_source is not None:
        return in_source, True
    if in_boundary is not None:
        if agg_kind == 'point' and in_source is not None:
            print(
                f'    Note: weight "{weight}" is defined for both the '
                'boundaries and the sample points; the boundary value is '
                'used, as sample points are equally weighted.',
            )
        return f'MAX(b."{in_boundary}")', False
    if in_source is not None:
        # only reachable for a point source, where a per-point weight cannot
        # meaningfully be summed for the boundary
        print(
            f'    Warning: weight "{weight}" was found in "{agg_source}" but '
            'not in the aggregation boundaries.  Sample points are equally '
            'weighted, so no population estimate can be derived; specify a '
            'weight variable present in the boundary data instead.',
        )
        return None, False
    print(
        f'    Warning: weight "{weight}" was not found in "{agg_source}" or '
        f'"{boundaries}"; skipping population weighting for this '
        'aggregation.',
    )
    return None, False


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
    # The aggregation below matches sample points / grid cells (and network
    # intersections) against each boundary with ST_Intersects / ST_DWithin.
    # grid_summary, point_summary and the (OSMnx) intersections table are all
    # written via geopandas to_postgis, which does NOT create a spatial index, so
    # without one these joins fall back to sequential scans -- effectively
    # O(boundaries x sample points) and pathologically slow for large regions.
    # A GiST index turns them into indexed lookups.  Creating it is idempotent
    # (IF NOT EXISTS) and cannot change the aggregation result.
    with r.engine.begin() as connection:
        connection.execute(
            text(
                f'CREATE INDEX IF NOT EXISTS '
                f'"{r.config["intersections_table"]}_gix" ON '
                f'"{r.config["intersections_table"]}" USING GIST (geom);',
            ),
        )
    for agg in r.config['custom_aggregations']:
        sql_agg = agg.replace(' ', '_').lower()
        table = f'indicators_{sql_agg}'
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
                agg_kind = agg_source
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
                agg_kind = 'area'
                agg_source = (
                    f"indicators_{agg_source.replace(' ', '_').lower()}"
                )
                count_units = 'area_count'
                indicator_list = indicators['output'][
                    'neighbourhood_variables'
                ]
            else:
                print(
                    f'    Aggregating source {agg_source} could not be identified; skipping.',
                )
                continue
        # spatially index the aggregation source (see note above); guarded on
        # existence so an unresolved/prior-agg source name is left to the query
        # below to report, and ANALYZE so the planner costs the join correctly on
        # the freshly written table.
        if agg_source in r.get_tables():
            with r.engine.begin() as connection:
                connection.execute(
                    text(
                        f'CREATE INDEX IF NOT EXISTS "{agg_source}_gix" ON '
                        f'"{agg_source}" USING GIST (geom);',
                    ),
                )
                connection.execute(text(f'ANALYZE "{agg_source}";'))
        agg_distance = r.config['custom_aggregations'][agg].pop(
            'aggregate_within_distance',
            None,
        )
        if agg_distance is not None:
            agg_on = f"""ST_DWithin(b.geom, s.geom, {int(agg_distance)})"""
            intersections_on = (
                f"""ST_DWithin(b.geom, x.geom, {int(agg_distance)})"""
            )
        else:
            agg_on = """ST_Intersects(b.geom, s.geom)"""
            intersections_on = """ST_Intersects(b.geom, x.geom)"""
        weight = r.config['custom_aggregations'][agg].pop('weight', None)
        area_weighted = r.config['custom_aggregations'][agg].pop(
            'area_weighted',
            True,
        )
        # A weight may describe the aggregation source or the boundaries; see
        # resolve_weight().  Weighted indicator estimates are only meaningful
        # where the source is areal and carries the weight itself.
        weight_column, weighted = resolve_weight(
            r,
            weight,
            boundaries,
            agg_source,
            agg_kind,
        )
        if weighted:
            # Source units straddling a boundary are apportioned by the share
            # of their area falling within it, so that a unit's population is
            # divided between the areas it spans rather than counted in full
            # in each.  Note that this assumes the weight is evenly
            # distributed within each unit, which may understate estimates for
            # areas bounded by unpopulated land or water (e.g. a coastline).
            # Apportionment is not applicable where aggregation is within a
            # distance of the boundary, as such catchments intentionally
            # overlap and need not intersect the aggregated units at all.
            if area_weighted and agg_distance is None:
                share = """ * GREATEST(LEAST(ST_Area(ST_Intersection(b.geom, s.geom)) / NULLIF(ST_Area(s.geom), 0), 1), 0)"""
            else:
                share = ''
            agg_weight = f"""COALESCE(SUM(s."{weight_column}"{share}),0)"""
            # using population weighting
            # if there are zero weights the indicator is null
            # else, calculate the value of the weighted indicator
            weighting = '''
                (CASE
                    WHEN COALESCE(SUM(s."{weight}"{share}),0) = 0
                        THEN NULL
                    ELSE
                        (SUM(s."{weight}"{share}*s."{i}"::float8)/SUM(s."{weight}"{share}))::float8
                END) AS "{weight}_{i}"
                '''
            agg_formula = ','.join(
                [
                    weighting.format(i=i, weight=weight_column, share=share)
                    for i in indicator_list
                ],
            )
        else:
            # Either no usable weight, or the weight belongs to the boundary
            # (a point source), in which case it is reported as the boundary's
            # population estimate but indicator estimates are unweighted.
            agg_weight = weight_column
            agg_formula = ','.join(
                [
                    f'''\n    {100.0 if name_mapping.get(i, '').startswith('pct') else 1.0} * AVG(s."{i}"::float8) AS "{name_mapping.get(i, "avg_" + i)}"'''
                    for i in indicator_list
                ],
            )
        # Intersections are counted against the boundary using a lateral
        # subquery returning a single row per boundary, applying the same
        # spatial relation used to aggregate indicators.  Joining the
        # intersections table directly would instead return one row per
        # aggregation unit *per intersection*, multiplying the aggregation
        # unit rows and thereby inflating the summed population weight, the
        # unit count, and the weighting applied to each indicator estimate.
        queries = [
            f"""DROP TABLE IF EXISTS {table};""",
            f"""CREATE TABLE "{table}" AS
    SELECT b.{id},
    {keep_columns if keep_columns.replace(',', '') != id else ''}
    ST_Area(b.geom)/10^6 AS area_sqkm,
    {agg_weight if agg_weight else 'NULL'} AS pop_est,
    {f'{agg_weight}/(ST_Area(b.geom)/10^6)' if agg_weight else 'NULL'} AS pop_per_sqkm,
    i.intersection_count,
    i.intersection_count/(ST_Area(b.geom)/10^6) AS intersections_per_sqkm,
    COUNT(s.*) AS {count_units},
    {agg_formula},
    b.geom
    FROM "{boundaries}" b
    LEFT JOIN LATERAL (
        SELECT COUNT(*) AS intersection_count
        FROM "{r.config['intersections_table'].lower()}" x
        WHERE {intersections_on}
    ) i ON TRUE
    LEFT JOIN "{agg_source}" s ON {agg_on}
    {query}
    GROUP BY b.{id}, {keep_columns} b.geom, i.intersection_count;""",
            f"""DELETE FROM {table} WHERE {count_units} = 0;""",
            f"""CREATE INDEX {table}_ix  ON {table} ({id});""",
            f"""CREATE INDEX {table}_gix ON {table} USING GIST(geom);""",
        ]
        for query in queries:
            try:
                print(query)
                with r.engine.begin() as connection:
                    connection.execute(text(query))
            except Exception as e:
                sys.exit(
                    f"Error when attempting to aggregate for {agg} '{boundary_data}' (check custom aggregation configuration): {e}",
                )
        # Registered once the aggregation has completed, so that a later
        # aggregation may in turn use this one as its source.
        processed_aggs.append(agg)


def calc_cycling_indicators(r: ghsci.Region) -> None:
    """Aggregate cycling sample-point indicators to the grid and city summaries.

    Gated by the region's cycling_indicators config.  Adds (does not replace) columns
    to the existing grid and city summary tables: per grid-cell mean access (as a
    percentage) and mean safe-route distance, plus the population-weighted city values.
    """
    from _cycling_accessibility import DMGAP_INFIX, MEASURES
    from _cycling_lts_network import cycling_config

    if (
        cycling_config(r) is None
        or 'sample_points_cycling' not in r.get_tables()
    ):
        return

    cols = r.get_df(
        'SELECT column_name FROM information_schema.columns '
        "WHERE table_name = 'sample_points_cycling'",
    )['column_name'].tolist()
    # every configured accessibility measure is aggregated: the measure's column infix
    # (e.g. 'safe_' for the low-stress LTS<=2 headline, 'lts1_' for the LTS-1-only
    # variant, none for danger-weighted) carries through from the sample-point columns
    # (sp_cycle_<infix>access_* / sp_cycle_<infix>nearest_node_*) to the grid and city
    # columns.  Whatever measures were run are picked up from the columns present.
    prefix_map = [
        (
            f'sp_cycle_{m["infix"]}access_',
            f'pct_access_cycle_{m["infix"]}',
            True,
        )
        for m in MEASURES.values()
    ] + [
        (
            f'sp_cycle_{m["infix"]}nearest_node_',
            f'avg_cycle_dist_{m["infix"]}',
            False,
        )
        for m in MEASURES.values()
    ] + [
        # paired with/without-dismount contrast (present only where both measures of
        # the dismount pair were run): the percentage of a cell's sample points whose
        # access depends on dismounting, and the mean extra riding distance needed to
        # avoid it (averaged over the points reachable both ways)
        (
            f'sp_cycle_{DMGAP_INFIX}access_',
            f'pct_access_cycle_{DMGAP_INFIX}',
            True,
        ),
        (
            f'sp_cycle_{DMGAP_INFIX}extra_',
            f'avg_cycle_extra_{DMGAP_INFIX}',
            False,
        ),
    ]

    def _classify(col):
        for src, dest, is_access in prefix_map:
            if col.startswith(src):
                return dest + col[len(src) :], is_access
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

    grid_summary = r.config['grid_summary']
    summary_cols = r.get_df(
        'SELECT column_name FROM information_schema.columns '
        f"WHERE table_name = '{grid_summary}'",
    )['column_name'].tolist()
    # grid-cell means: access proportions -> percentages, distances kept in metres
    if 'grid_id' in summary_cols:
        key = 'grid_id'
        sp = r.get_df(
            f'SELECT grid_id, {", ".join(value_cols)} '
            'FROM sample_points_cycling',
        )
        grid = sp.groupby('grid_id')[value_cols].mean()
    else:
        # Custom population regions (e.g. vector census areas) summarise
        # indicators for areas spatially associated with sample points rather
        # than a grid; mirror the region's configured custom point aggregation
        # distance when averaging cycling sample point values for each area.
        key = 'ogc_fid'
        custom_population = r.config['population'].get('custom_population')
        distance = (
            (r.config.get('custom_aggregations') or {})
            .get(custom_population, {})
            .get('aggregate_within_distance', 30)
        )
        with r.engine.begin() as connection:
            connection.execute(
                text(
                    'CREATE INDEX IF NOT EXISTS sample_points_cycling_gix '
                    'ON sample_points_cycling USING GIST (geom);',
                ),
            )
        agg_clause = ', '.join(f'AVG(s."{c}") AS "{c}"' for c in value_cols)
        grid = r.get_df(
            f'SELECT b."{key}", {agg_clause} '
            f'FROM "{grid_summary}" b '
            'JOIN sample_points_cycling s '
            f'ON ST_DWithin(b.geom, s.geom, {distance}) '
            f'GROUP BY b."{key}"',
        ).set_index(key)
    for c in access_cols:
        grid[c] = grid[c] * 100
    grid = grid.rename(columns=rename).reset_index()
    grid_value_cols = [rename[c] for c in value_cols]
    grid.to_sql('_cycling_grid', r.engine, if_exists='replace', index=False)
    with r.engine.begin() as conn:
        for col in grid_value_cols:
            conn.execute(
                text(
                    f'ALTER TABLE {grid_summary} ADD COLUMN IF NOT EXISTS '
                    f'"{col}" double precision',
                ),
            )
        set_clause = ', '.join(
            f'"{col}" = t."{col}"' for col in grid_value_cols
        )
        conn.execute(
            text(
                f'UPDATE {grid_summary} g SET {set_clause} '
                f'FROM _cycling_grid t WHERE g."{key}" = t."{key}"',
            ),
        )
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
            conn.execute(
                text(
                    f'ALTER TABLE {city_summary} ADD COLUMN IF NOT EXISTS '
                    f'"{col}" double precision',
                ),
            )
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
    calc_grid_pct_sp_indicators(r, r.indicators)

    print('\nCalculating custom aggregation indicators... ')
    custom_aggregation(r, r.indicators)

    print('\nCalculating city summary indicators... ')
    # Calculate city-level indicators weighted by population
    # calc_cities_pop_pct_indicators function take grid cell indicators and
    # pop estimates of each city as input then aggregate grid cell to city-level
    # indicator by summing all the population weighted grid cell indicators

    # in addition to the population weighted averages, unweighted averages are
    # also included to reflect the spatial distribution of key walkability
    # measures (regardless of population distribution)
    calc_cities_pop_pct_indicators(r, r.indicators)

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