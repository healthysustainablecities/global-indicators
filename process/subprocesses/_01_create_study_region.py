"""Set up study region boundaries."""

import os
import sys
import time

# Set up project and region parameters for GHSCIC analyses
import ghsci
from script_running_log import script_running_log
from sqlalchemy import text


def create_study_region(codename):
    """Set up study region boundaries."""
    start = time.time()
    script = '_01_create_study_region'
    task = 'create study region boundary'
    r = ghsci.Region(codename)
    name = r.config['name']
    crs_srid = r.config['crs_srid']
    db = r.config['db']
    db_host = r.config['db_host']
    db_port = r.config['db_port']
    db_user = r.config['db_user']
    db_pwd = r.config['db_pwd']
    # Create study region folder if not exists
    if not os.path.exists(
        f'{ghsci.folder_path}/process/data/_study_region_outputs',
    ):
        os.makedirs(f'{ghsci.folder_path}/process/data/_study_region_outputs')
    if not os.path.exists(r.config['region_dir']):
        os.makedirs(r.config['region_dir'])
    print('Create study region boundary... ')
    # import study region policy-relevant administrative boundary, or GHS boundary
    try:
        area_data = r.config['study_region_boundary']['data']
        urban_intersection = r.config['study_region_boundary'].pop(
            'urban_intersection',
            False,
        )
        if area_data == 'urban_query':
            # Global Human Settlements urban area is used to define this study region
            boundary_data = r.config['urban_region']['data_dir']
            query = f""" -where "{r.config['urban_query'].split(':')[1]}" """
            if '=' not in query:
                raise Exception(
                    """
                    The urban area configured for the study region was indicated,
                    however the query wasn't understood
                    (should be in format "GHS:field=value",
                     e.g. "GHS:UC_NM_MN=Baltimore, or (even better; more specific)
                          "GHS:UC_NM_MN='Baltimore' and CTR_MN_NM=='United States'"
                    """,
                )
        elif '.gpkg:' in area_data:
            gpkg = area_data.split(':')
            boundary_data = gpkg[0]
            query = gpkg[1]
        else:
            feature = area_data.split('-where ')
            boundary_data = feature[0].strip()
            if len(feature) > 1:
                query = f'-where {feature[1]}'
            else:
                query = ''
        r.ogr_to_db(
            source=boundary_data,
            layer='study_region_boundary',
            query=query,
            promote_to_multi=True,
        )
    except Exception as e:
        raise Exception(f'Error reading in boundary data (check format): {e}')
    print('\nCreate urban region boundary... ', end='', flush=True)
    if area_data.startswith('GHS:') or not urban_intersection:
        # e.g. Vic is not represented in the GHS data, so intersection is not used
        for table in ['urban_region', 'urban_study_region']:
            sql = f"""
                CREATE TABLE IF NOT EXISTS {table} AS
                SELECT '{name}'::text AS "study_region",
                       '{db}'::text AS "db",
                       ST_Area(geom)/10^6 AS area_sqkm,
                       geom
                FROM "study_region_boundary";
                CREATE INDEX IF NOT EXISTS {table}_gix ON {table} USING GIST (geom);
                """
            with r.engine.begin() as connection:
                connection.execute(text(sql))
    else:
        # Global Human Settlements urban area is used to define this study region
        if r.config['urban_query'] is not None:
            if '=' not in r.config['urban_query']:
                raise Exception(
                    """
                    The urban area configured for the study region was indicated,
                    however the query wasn't understood
                    (should be in format "GHS:field=value",
                     e.g. "GHS:UC_NM_MN=Baltimore, or (even better; more specific)
                          "GHS:UC_NM_MN='Baltimore' and CTR_MN_NM=='United States'"
                    """,
                )
            else:
                query = (
                    f""" -where "{r.config['urban_query'].split(':')[1]}" """
                )
                additional_sql = ''
        else:
            # get study region bounding box to be used to retrieve intersecting urban geometries
            sql = """
                SELECT
                    ST_Xmin(geom) xmin,
                    ST_Ymin(geom) ymin,
                    ST_Xmax(geom) xmax,
                    ST_Ymax(geom) ymax
                FROM "study_region_boundary";
                """
            with r.engine.begin() as connection:
                result = connection.execute(text(sql))
                bbox = ' '.join(
                    [str(coord) for coord in [coords for coords in result][0]],
                )
            query = f' -spat {bbox} -spat_srs {crs_srid}'
            additional_sql = """
                ,"study_region_boundary" b
                    WHERE ST_Intersects(a.geom, b.geom);
               """    
        if '.gpkg:' in r.config['urban_region']['data_dir']:
            gpkg = r.config['urban_region']['data_dir'].split(':')
            urban_region_data = gpkg[0]
            query = f"{query} {gpkg[1]}"
        else:
            feature = r.config['urban_region']['data_dir'].split('-where ')
            urban_region_data = feature[0].strip()
            if len(feature) > 1:
                query = f'{query} -where {feature[1]}'
        r.ogr_to_db(
            source=urban_region_data,
            layer='full_urban_region',
            query=query,
            promote_to_multi=True,
        )
        sql = f"""
           CREATE TABLE IF NOT EXISTS urban_region AS
           SELECT '{name}'::text AS "study_region",
                  '{db}'::text AS "db",
                  ST_Area(a.geom)/10^6 AS area_sqkm,
                  a.geom
           FROM full_urban_region a
           {additional_sql};
           CREATE INDEX IF NOT EXISTS urban_region_gix ON urban_region USING GIST (geom);
           """
        with r.engine.begin() as connection:
            connection.execute(text(sql))
        sql = """
           CREATE TABLE IF NOT EXISTS urban_study_region AS
           SELECT b."study_region",
                  b."db",
                  ST_Area(ST_Union(ST_Intersection(a.geom,b.geom)))/10^6 AS area_sqkm,
                  ST_Union(ST_Intersection(a.geom,b.geom)) geom
           FROM "study_region_boundary" a,
                urban_region b
           GROUP BY b."study_region", b."db";
           CREATE INDEX IF NOT EXISTS urban_study_region_gix ON urban_study_region USING GIST (geom);
           """
        with r.engine.begin() as connection:
            connection.execute(text(sql))
        print('Done.')

    print(
        f'\nCreate {ghsci.settings["project"]["study_buffer"]} m buffered study region... ',
        end='',
        flush=True,
    ),
    study_buffer_km = ghsci.settings['project']['study_buffer'] / 1000
    buffered_urban_study_region_extent = f'{study_buffer_km} km'
    sql = f"""
    CREATE TABLE IF NOT EXISTS {r.config['buffered_urban_study_region']} AS
          SELECT "study_region",
                 db,
                 '{buffered_urban_study_region_extent}'::text AS "Study region buffer",
                 ST_Buffer(geom,{ghsci.settings["project"]["study_buffer"]}) AS geom
            FROM  urban_study_region ;
    CREATE INDEX IF NOT EXISTS {r.config['buffered_urban_study_region']}_gix ON
        {r.config['buffered_urban_study_region']} USING GIST (geom);
    """
    with r.engine.begin() as connection:
        connection.execute(text(sql))
    print('Done.')
    if {
        'study_region_boundary',
        'urban_region',
        'urban_study_region',
        r.config['buffered_urban_study_region'],
    }.issubset(r.get_tables()):
        print(
            f"""\nThe following layers have been created:
        \n- study_region_boundary: To represent a policy-relevant administrative boundary (or proxy for this).
        \n- urban_region: Representing the urban area surrounding the study region.
        \n- urban_study_region: The urban portion of the policy-relevant study region.
        \n- {r.config['buffered_urban_study_region']}: An analytical boundary extending {ghsci.settings["project"]["study_buffer"]} {ghsci.settings["project"]["units"]} further to mitigate edge effects.
        """,
        )
        print(
            f"""If you wish to recreate these tables, please manually drop them (e.g. using psql) or optionally drop the {db} database and start again (e.g. using the subprocesses/_drop_study_region_database.py utility script.\n""",
        )
    else:
        raise Exception(
            """Study region boundary creation failed; check configuration and log files to identify specific issues.""",
        )
    # output to completion log
    script_running_log(r.config, script, task, start)
    r.engine.dispose()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    create_study_region(codename)


if __name__ == '__main__':
    main()
