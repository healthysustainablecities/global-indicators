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


def clipped_boundary_sql(clip, boundaries: str, srid) -> tuple:
    """Return SQL for aggregation boundaries, optionally clipped.

    The analytical area of a study region is its urban study region, so by
    default each aggregation boundary is restricted to the part of it that was
    actually analysed.  Reporting a boundary's full extent alongside indicators
    derived only from part of it would overstate its area and understate every
    density derived from it.  The boundaries as configured are retained
    unchanged in the corresponding "agg_" table, so that the two may be
    overlaid to see what each area did and did not contribute.

    Returns (prelude, geometry, source), where prelude is a common table
    expression to precede the SELECT (empty where boundaries are not clipped),
    geometry is the expression to use wherever the boundary geometry is
    required, and source is the FROM clause naming the boundaries.
    """
    if not clip:
        return '', 'b.geom', f'"{boundaries}" b'
    # MATERIALIZED, and not optionally: PostgreSQL inlines a CTE referenced
    # once, which substitutes this ST_Intersection into every reference to the
    # clipped geometry -- and those references sit inside aggregates evaluated
    # per *join row*, not per boundary.  Measured over the manzanas joined to
    # their sample points, inlining cost 246s against 5.9s materialised, and
    # took a full Mexicali aggregation from 16 minutes to 100.
    prelude = f"""WITH clipped AS MATERIALIZED (
        SELECT b.*,
               ST_Multi(
                   ST_CollectionExtract(
                       ST_Intersection(b.geom, u.geom), 3
                   )
               )::geometry(MultiPolygon, {srid})
                   AS analysed_geom
        FROM "{boundaries}" b,
             (SELECT ST_Union(geom) AS geom FROM urban_study_region) u
        WHERE ST_Intersects(b.geom, u.geom)
    ), analysed AS MATERIALIZED (
        -- Boundaries that merely touch the urban study region along an edge
        -- intersect it in a line or a point, and clip to an empty polygon.
        -- They contributed nothing to the analysis, and retaining them would
        -- divide by an area of zero when deriving densities.
        SELECT * FROM clipped WHERE ST_Area(analysed_geom) > 0
    )
    """
    return prelude, 'b.analysed_geom', 'analysed b'


def custom_data_load(r: ghsci.Region, agg) -> str:
    try:
        boundary_data = r.config['custom_aggregations'][agg]['data']
        sql_agg = agg.replace(' ', '_').lower()
        table = f'agg_{sql_agg}'
        if '.gpkg:' in boundary_data:
            gpkg = boundary_data.split(':')
            source = gpkg[0]
            query = gpkg[1]
        else:
            # Features may be filtered with an attribute query, as they may be
            # for the study region boundary and urban region.  The query is not
            # part of the path and has to be separated from it before use;
            # leaving it embedded yields a path that cannot be opened.
            feature = boundary_data.split('-where ')
            source = feature[0].strip()
            query = f'-where {feature[1]}' if len(feature) > 1 else ''
        source = f'/home/ghsci/process/data/{source}'
        if '.zip' in source:
            # allow for GDAL Virtual File Systems, so that data may be
            # configured as distributed (e.g. a zipped shapefile) without
            # having to be unpacked first
            source = f'/vsizip//{source}'
        command = (
            '            ogr2ogr -overwrite -progress -f "PostgreSQL" '
            f' PG:"host={r.config["db_host"]} port={r.config["db_port"]} dbname={r.config["db"]}'
            f' user={r.config["db_user"]} password={r.config["db_pwd"]}" '
            f' "{source}" '
            f' -lco geometry_name="geom" -lco precision=NO '
            f' -t_srs {r.config["crs_srid"]} -nln "{table}" '
            f' -nlt PROMOTE_TO_MULTI -makevalid'
            f' {query}'
        )
        print(command)
        failure = sp.call(command, shell=True)
        if failure != 0:
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


def qualify_keep_columns(keep_columns, id: str, boundary_columns: dict) -> str:
    """Return configured additional boundary attributes as a SQL fragment.

    Each retained column is qualified as belonging to the aggregation
    boundaries ('b'), so that a name also present in the aggregation source
    ('s') --- as occurs where an aggregation summarises another which
    retained a column of the boundaries used here --- is not ambiguous.

    Names matching the identifier are omitted, as it is already selected.
    Configured names are matched case insensitively, because column names
    are lower cased when boundary data is imported.

    The fragment is comma terminated for interpolation before a following
    expression, or empty where no columns are to be retained.
    """
    retained = []
    for column in str(keep_columns or '').split(','):
        column = column.strip().lower()
        if column in ['', str(id).lower()]:
            continue
        # reference the column as imported, where it can be identified, so
        # that quoting it does not make the configured name case sensitive
        retained.append(f'b."{boundary_columns.get(column, column)}"')
    if retained == []:
        return ''
    columns = ', '.join(retained)
    return f'{columns},'


def resolve_output_names(indicators: dict, agg_kind: str, weighted: bool):
    """Map each source indicator column to its output name and scale.

    Returns a list of (source_column, output_column, scale) tuples, where
    scale is the factor by which the source value is multiplied.

    Output naming does not depend on which variable was used as the
    weight.  A weighted estimate always takes the region level variable
    name (pop_walkability) and an unweighted one the neighbourhood
    variable name (local_walkability), so that every aggregation of a
    region reports the same indicators under the same names and any two
    may be compared row for row.  The weight that was applied is reported
    as pop_est, and recorded in the region's parameters; it is not
    encoded in the column names.

    Sample point variables are proportions, so the accessibility measures
    among them are scaled to percentages, as they are for the population
    grid.  Areal sources have already been scaled and are not rescaled.

    The sample point, neighbourhood and region level variable lists are
    positionally parallel; this is the only place that relies on that.
    """
    sample_point_variables = indicators['output']['sample_point_variables']
    neighbourhood_variables = indicators['output']['neighbourhood_variables']
    city_variables = indicators['output']['city_variables']
    if agg_kind == 'point':
        return [
            (
                sp,
                nb,
                100.0 if nb.startswith('pct_') else 1.0,
            )
            for sp, nb in zip(sample_point_variables, neighbourhood_variables)
        ]
    return [
        (nb, cy if weighted else nb, 1.0)
        for nb, cy in zip(neighbourhood_variables, city_variables)
    ]


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

    A numeric weight is a constant: each output row receives that value as
    pop_est regardless of source type.  Indicators are unweighted (a constant
    weight has no effect on a weighted average).
    """
    if weight in [None, 'false', False, 'False']:
        return None, False
    if isinstance(weight, (int, float)):
        return str(float(weight)), False
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


def custom_aggregation(r: ghsci.Region, indicators: dict) -> list:
    """Aggregate indicators for custom areas.

    Returns the resolved aggregation plan --- one entry per area that was
    actually built, in the order they were built --- so that the configurable
    configurable accessibility columns can be aggregated along the same path
    afterwards.  They cannot re-derive it: an area sourced from another area
    needs that area's table to exist before its weight column can be found, and
    the fixed indicator list this function works from does not contain them.
    """
    processed_aggs = []
    plans = []
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
        # read, never popped: the resolved plan is returned instead, and a
        # configuration that quietly empties itself as it is used cannot be
        # consulted twice (which is how these columns came to bypass it)
        keep_columns = r.config['custom_aggregations'][agg].get(
            'keep_columns',
            '',
        )
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
            id = r.config['custom_aggregations'][agg].get('id', 'ogc_fid')
            if id is None:
                id = 'ogc_fid'
            query = ''
        # The analytical area of a study region is its urban study region, so
        # by default each aggregation boundary is restricted to the part of it
        # that was actually analysed.  Set clip to false to summarise and
        # report the configured boundaries in full instead.
        clip = r.config['custom_aggregations'][agg].get('clip', True)
        _, boundary_geom, _ = clipped_boundary_sql(
            clip,
            None,
            r.config['crs']['srid'],
        )
        keep_columns = qualify_keep_columns(
            keep_columns,
            id,
            table_columns(r, boundaries),
        )
        agg_source = r.config['custom_aggregations'][agg].get(
            'aggregation_source',
            None,
        )
        if agg_source is None:
            print('    No aggregation source specified, skipping.')
            continue
        else:
            if agg_source in ['point', 'grid']:
                agg_kind = agg_source
                count_units = (
                    'urban_sample_point_count'
                    if agg_source == 'point'
                    else 'grid_count'
                )
                agg_source = r.config[f'{agg_source}_summary']
            elif agg_source in processed_aggs:
                # unclear if this will always be appropriate; may need customisation
                agg_kind = 'area'
                agg_source = (
                    f"indicators_{agg_source.replace(' ', '_').lower()}"
                )
                count_units = 'area_count'
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
        agg_distance = r.config['custom_aggregations'][agg].get(
            'aggregate_within_distance',
            None,
        )
        if agg_distance is not None:
            agg_on = (
                f"""ST_DWithin({boundary_geom}, s.geom, {int(agg_distance)})"""
            )
            intersections_on = (
                f"""ST_DWithin({boundary_geom}, x.geom, {int(agg_distance)})"""
            )
        else:
            agg_on = f"""ST_Intersects({boundary_geom}, s.geom)"""
            intersections_on = f"""ST_Intersects({boundary_geom}, x.geom)"""
        weight = r.config['custom_aggregations'][agg].get('weight', None)
        # population_estimate is a deprecated alias; use weight: <number> instead
        population_estimate = r.config['custom_aggregations'][agg].get(
            'population_estimate',
            None,
        )
        if population_estimate is not None and weight is None:
            print(
                f'    Note: "population_estimate" is deprecated; '
                f'use "weight: {population_estimate}" instead.',
            )
            weight = population_estimate
        area_weighted = r.config['custom_aggregations'][agg].get(
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
                share = f""" * GREATEST(LEAST(ST_Area(ST_Intersection({boundary_geom}, s.geom)) / NULLIF(ST_Area(s.geom), 0), 1), 0)"""
            else:
                share = ''
            agg_weight = f"""COALESCE(SUM(s."{weight_column}"{share}),0)"""
            # using weighting
            # if there are zero weights the indicator is null
            # else, calculate the value of the weighted indicator
            weighting = '''
                (CASE
                    WHEN COALESCE(SUM(s."{weight}"{share}),0) = 0
                        THEN NULL
                    ELSE
                        (SUM(s."{weight}"{share}*s."{i}"::float8)/SUM(s."{weight}"{share}))::float8
                END) AS "{col}"
                '''
            agg_formula = ','.join(
                [
                    weighting.format(
                        i=source,
                        weight=weight_column,
                        share=share,
                        col=output,
                    )
                    for source, output, _ in resolve_output_names(
                        indicators,
                        agg_kind,
                        True,
                    )
                ],
            )
            # Mirror the city summary: append extra_unweighted_vars as plain
            # unweighted means alongside their weighted counterparts, so that
            # the two may be distinguished.  Weighted estimates have been
            # renamed to the region level variable names, so these do not
            # collide with them.
            extra = [
                v
                for v in indicators['output'].get('extra_unweighted_vars', [])
                if v in indicators['output']['neighbourhood_variables']
            ]
            if extra and agg_kind != 'point':
                agg_formula += ', ' + ', '.join(
                    f'\n    AVG(s."{v}"::float8) AS "{v}"' for v in extra
                )
        else:
            # Either no usable weight, or the weight belongs to the boundary
            # (a point source), in which case it is reported as the boundary's
            # population estimate but indicator estimates are unweighted.
            agg_weight = weight_column
            agg_formula = ','.join(
                [
                    f'''\n    {scale} * AVG(s."{source}"::float8) AS "{output}"'''
                    for source, output, scale in resolve_output_names(
                        indicators,
                        agg_kind,
                        False,
                    )
                ],
            )
        # Intersections are counted against the boundary using a lateral
        # subquery returning a single row per boundary, applying the same
        # spatial relation used to aggregate indicators.  Joining the
        # intersections table directly would instead return one row per
        # aggregation unit *per intersection*, multiplying the aggregation
        # unit rows and thereby inflating the summed population weight, the
        # unit count, and the weighting applied to each indicator estimate.
        prelude, _, source_clause = clipped_boundary_sql(
            clip,
            boundaries,
            r.config['crs']['srid'],
        )
        queries = [
            f"""DROP TABLE IF EXISTS {table};""",
            f"""CREATE TABLE "{table}" AS
    {prelude}SELECT b.{id},
    {keep_columns}
    ST_Area({boundary_geom})/10^6 AS area_sqkm,
    {agg_weight if agg_weight else 'NULL'} AS pop_est,
    {f'{agg_weight}/NULLIF(ST_Area({boundary_geom})/10^6, 0)' if agg_weight else 'NULL'} AS pop_per_sqkm,
    i.intersection_count,
    i.intersection_count/NULLIF(ST_Area({boundary_geom})/10^6, 0) AS intersections_per_sqkm,
    COUNT(s.*) AS {count_units},
    {agg_formula},
    {boundary_geom} AS geom
    FROM {source_clause}
    LEFT JOIN LATERAL (
        SELECT COUNT(*) AS intersection_count
        FROM "{r.config['intersections_table'].lower()}" x
        WHERE {intersections_on}
    ) i ON TRUE
    LEFT JOIN "{agg_source}" s ON {agg_on}
    {query}
    GROUP BY b.{id}, {keep_columns} {boundary_geom}, i.intersection_count;""",
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
        plans.append(
            {
                'name': agg,
                'table': table,
                'id': id,
                'agg_kind': agg_kind,
                'source_table': agg_source,
                'agg_distance': agg_distance,
                'weight_column': weight_column,
                'weighted': weighted,
                'area_weighted': area_weighted,
            },
        )
    return plans


def _custom_area_query(
    plan,
    area_table,
    area_id,
    source,
    predicate,
    columns,
    source_columns,
    scale,
):
    """The sub-select giving each custom area its value for each column.

    Mirrors custom_aggregation()'s own weighting, because it is summarising the
    same units by the same rule --- only over columns that the fixed indicator
    list does not contain.

    ``point``  an unweighted mean of the sample points within the configured
               distance.  Sample-point access columns are proportions, so they
               are scaled to percentages here exactly as they are on their way
               to the grid; an area summarised from another *area* must not be
               scaled again, its source values already being percentages.
    ``grid`` / ``area``
               weighted by the source's own weight where it has one, falling
               back to an unweighted mean where the weight sums to zero: a new
               development may be fully built and routable while recording no
               residents, and a null there would be worse than a mean.

    The weight is computed **once per (area, unit) pair**, in a CTE marked
    MATERIALIZED.  Where a unit straddling the boundary is apportioned by area
    that expression is an ST_Intersection of two polygons, and repeating it
    across 310 aggregates against a region-sized multipolygon does not finish in
    any useful time: Mexicali's region summary ran an hour and three quarters on
    one UPDATE before it was stopped.  The fence is the point of the CTE --- a
    plain sub-select is flattened, which substitutes the expression back into
    every one of the 620 places the aggregates refer to it, and the hoisting
    achieves nothing.  See also the ST_CoveredBy short-circuit below.
    """
    pairs = (
        f'SELECT b."{area_id}" AS area_key, {{weight}} '
        f'{{values}} FROM {area_table} b '
        f'JOIN "{source}" s ON {predicate}'
    )

    def wrap(inner, aggregates):
        return (
            f'WITH pairs AS MATERIALIZED ({inner}) '
            f'SELECT area_key, {aggregates} FROM pairs p GROUP BY area_key'
        )

    if plan['agg_kind'] == 'point':
        values = ''.join(
            f', {scale(src)} * s."{src}"::float8 AS "{col}"'
            for src, col in zip(source_columns, columns)
        )
        inner = pairs.format(weight='1.0 AS w', values=values)
        aggregates = ', '.join(f'AVG(p."{col}") AS "{col}"' for col in columns)
        return wrap(inner, aggregates)

    values = ''.join(f', s."{col}"::float8 AS "{col}"' for col in columns)
    weight = plan['weight_column']
    if not plan['weighted'] or not weight:
        inner = pairs.format(weight='1.0 AS w', values=values)
        aggregates = ', '.join(f'AVG(p."{col}") AS "{col}"' for col in columns)
        return wrap(inner, aggregates)

    # Source units straddling a boundary are apportioned by the share of their
    # area falling within it, as in custom_aggregation().  Not applicable where
    # aggregation is within a distance of the boundary, as such catchments
    # intentionally overlap.
    #
    # ST_CoveredBy first: a unit wholly inside the boundary contributes its
    # whole weight, and deciding that is an indexed containment test rather than
    # a clip of the boundary's outline.  For a study region that contains nearly
    # all of its grid cells this reduces the intersections computed from every
    # cell to only those on the edge.
    share = (
        ' * CASE WHEN ST_CoveredBy(s.geom, b.geom) THEN 1.0 ELSE'
        ' GREATEST(LEAST(ST_Area(ST_Intersection(b.geom, s.geom))'
        ' / NULLIF(ST_Area(s.geom), 0), 1), 0) END'
        if plan['area_weighted'] and plan['agg_distance'] is None
        else ''
    )
    inner = pairs.format(
        weight=f's."{weight}"::float8{share} AS w',
        values=values,
    )
    aggregates = ', '.join(
        f'COALESCE('
        f'SUM(p.w * p."{col}") FILTER (WHERE p."{col}" IS NOT NULL) '
        f'/ NULLIF(SUM(p.w) FILTER (WHERE p."{col}" IS NOT NULL), 0), '
        f'AVG(p."{col}")) AS "{col}"'
        for col in columns
    )
    return wrap(inner, aggregates)


def _propagate_sample_point_columns(
    r: ghsci.Region,
    table: str,
    prefix_map: list,
    label: str,
    plans: list = None,
) -> None:
    """Aggregate configurable sample-point columns to grid, city and custom areas.

    Shared by the configurable accessibility analyses, whose output columns
    are derived from whichever destinations, distances and measures a region
    configured and so cannot be listed in indicators.yml's fixed, positionally
    parallel output lists.  Adds (does not replace) columns to the existing summary
    tables.

    ``prefix_map`` is an ordered list of ``(sample_point_prefix, output_prefix,
    is_access)`` triples; the sample-point columns present are classified by the first
    matching prefix, renamed by substituting the output prefix, and averaged.  Access
    proportions (``is_access``) are scaled to percentages; distances stay in metres.
    """
    cols = r.get_df(
        'SELECT column_name FROM information_schema.columns '
        f"WHERE table_name = '{table}'",
    )['column_name'].tolist()

    def _classify(col):
        for source, dest, is_access in prefix_map:
            if col.startswith(source):
                return dest + col[len(source) :], is_access
        return None, None

    rename, access_cols, value_cols = {}, [], []
    for c in cols:
        new_name, is_access = _classify(c)
        if new_name is None:
            continue
        rename[c] = new_name
        value_cols.append(c)
        if is_access:
            access_cols.append(c)
    if 'grid_id' not in cols or not value_cols:
        return

    stage_table = f'_{label}_grid'
    grid_summary = r.config['grid_summary']
    summary_cols = r.get_df(
        'SELECT column_name FROM information_schema.columns '
        f"WHERE table_name = '{grid_summary}'",
    )['column_name'].tolist()
    # grid-cell means: access proportions -> percentages, distances kept in metres
    if 'grid_id' in summary_cols:
        key = 'grid_id'
        sp = r.get_df(
            f'SELECT grid_id, {", ".join(value_cols)} FROM {table}',
        )
        grid = sp.groupby('grid_id')[value_cols].mean()
    else:
        # Custom population regions (e.g. vector census areas) summarise
        # indicators for areas spatially associated with sample points rather
        # than a grid; mirror the region's configured custom point aggregation
        # distance when averaging sample point values for each area.
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
                    f'CREATE INDEX IF NOT EXISTS {table}_gix '
                    f'ON {table} USING GIST (geom);',
                ),
            )
        agg_clause = ', '.join(f'AVG(s."{c}") AS "{c}"' for c in value_cols)
        grid = r.get_df(
            f'SELECT b."{key}", {agg_clause} '
            f'FROM "{grid_summary}" b '
            f'JOIN {table} s '
            f'ON ST_DWithin(b.geom, s.geom, {distance}) '
            f'GROUP BY b."{key}"',
        ).set_index(key)
    for c in access_cols:
        grid[c] = grid[c] * 100
    grid = grid.rename(columns=rename).reset_index()
    grid_value_cols = [rename[c] for c in value_cols]
    grid.to_sql(stage_table, r.engine, if_exists='replace', index=False)
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
                f'FROM {stage_table} t WHERE g."{key}" = t."{key}"',
            ),
        )
        conn.execute(text(f'DROP TABLE IF EXISTS {stage_table}'))

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
    aggregated_to = ['grid', 'city']

    # Custom aggregation areas are built from the fixed indicator list in
    # indicators.yml, which cannot contain these columns: they are derived from
    # whichever destinations, distances and measures a region configured.  They
    # are therefore aggregated here -- but along the *same* path the area's own
    # configuration describes, which is what custom_aggregation() resolved and
    # handed back.  Carrying them across from the population grid instead (as
    # this once did) silently overrode `aggregation_source` and `weight`: a
    # development summarised from its own lots was summarised from the 100 m
    # grid, and weighted by whatever population that grid recorded rather than
    # by the lots' own.
    #
    # Iterated in the order the areas were built, so that an area sourced from
    # another reads values that have already been written.
    def scale(column):
        return 100.0 if column in access_cols else 1.0

    with r.engine.begin() as connection:
        connection.execute(
            text(
                f'CREATE INDEX IF NOT EXISTS {table}_gix '
                f'ON {table} USING GIST (geom);',
            ),
        )
    for plan in plans or []:
        area_table = plan['table']
        if area_table not in r.get_tables():
            continue
        # Read back from the table, not from the plan: custom_aggregation()
        # writes the identifier unquoted, so a configured "CVEGEO" is folded to
        # "cvegeo" on the way in and quoting the configured spelling here would
        # not resolve.  It is written as the first column.
        area_id = r.get_df(
            'SELECT column_name FROM information_schema.columns '
            f"WHERE table_name = '{area_table}' ORDER BY ordinal_position "
            'LIMIT 1',
        )['column_name'].iloc[0]
        # a point source carries the sample-point columns themselves; an areal
        # source carries the renamed, already-scaled ones
        if plan['agg_kind'] == 'point':
            source, source_columns = table, value_cols
            predicate = (
                f'ST_DWithin(b.geom, s.geom, {int(plan["agg_distance"])})'
                if plan['agg_distance'] is not None
                else 'ST_Intersects(b.geom, s.geom)'
            )
        else:
            source = (
                grid_summary
                if plan['agg_kind'] == 'grid'
                else plan['source_table']
            )
            source_columns = grid_value_cols
            predicate = 'ST_Intersects(b.geom, s.geom)'
        summary = _custom_area_query(
            plan,
            area_table,
            area_id,
            source,
            predicate,
            grid_value_cols,
            source_columns,
            scale,
        )
        with r.engine.begin() as conn:
            for col in grid_value_cols:
                conn.execute(
                    text(
                        f'ALTER TABLE {area_table} ADD COLUMN IF NOT EXISTS '
                        f'"{col}" double precision',
                    ),
                )
            set_clause = ', '.join(
                f'"{col}" = t."{col}"' for col in grid_value_cols
            )
            conn.execute(
                text(
                    f'UPDATE {area_table} a SET {set_clause} '
                    f'FROM ({summary}) t WHERE a."{area_id}" = t.area_key',
                ),
            )
        aggregated_to.append(
            f'{plan["name"]} (from {plan["agg_kind"]})',
        )

    print(
        f'  - {label}: aggregated {len(grid_value_cols)} indicators to the '
        + ', '.join(aggregated_to)
        + ' summaries',
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
    plans = custom_aggregation(r, r.indicators)

    print('\nCalculating city summary indicators... ')
    # Calculate city-level indicators weighted by population
    # calc_cities_pop_pct_indicators function take grid cell indicators and
    # pop estimates of each city as input then aggregate grid cell to city-level
    # indicator by summing all the population weighted grid cell indicators

    # in addition to the population weighted averages, unweighted averages are
    # also included to reflect the spatial distribution of key walkability
    # measures (regardless of population distribution)
    calc_cities_pop_pct_indicators(r, r.indicators)

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
