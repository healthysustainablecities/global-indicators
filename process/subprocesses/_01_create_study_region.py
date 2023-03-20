"""
Define study region.

Python set up study region boundaries and associated population
resources.
"""

import os
import subprocess as sp
import time

import geopandas as gpd
import numpy as np
import pandas as pd

# Set up project and region parameters for GHSCIC analyses
from _project_setup import *
from geoalchemy2 import Geometry, WKTElement
from script_running_log import script_running_log
from shapely.geometry import MultiPolygon, Polygon
from sqlalchemy import create_engine, inspect, text


def main():
    # simple timer for log file
    start = time.time()
    script = os.path.basename(sys.argv[0])
    task = 'create study region boundary'
    # Create study region folder if not exists
    if not os.path.exists(f'{folder_path}/process/data/_study_region_outputs'):
        os.makedirs(f'{folder_path}/process/data/_study_region_outputs')
    if not os.path.exists(region_dir):
        os.makedirs(region_dir)
    engine = create_engine(
        f'postgresql://{db_user}:{db_pwd}@{db_host}/{db}', future=True,
    )
    db_contents = inspect(engine)
    if (
        db_contents.has_table(study_region)
        and db_contents.has_table('urban_region')
        and db_contents.has_table('urban_study_region')
        and db_contents.has_table(buffered_urban_study_region)
    ):
        return f"""Study region boundaries have previously been created ({study_region}, urban_region, urban_study_region and {buffered_urban_study_region}).   If you wish to recreate these, please manually drop them (e.g. using psql) or optionally drop the {db} database and start again (e.g. using the subprocesses/_drop_study_region_database.py utility script.\n"""
    print('Create study region boundary... ')
    # import study region policy-relevant administrative boundary, or GHS boundary
    try:
        area_data = study_region_boundary['data']
        if area_data == 'urban_query':
            # Global Human Settlements urban area is used to define this study region
            boundary_data = urban_region['data_dir']
            query = f""" -where "{urban_query.split(':')[1]}" """
            if '=' not in query:
                raise (
                    """
                    The urban area configured for the study region was indicated,
                    however the query wasn't understood
                    (should be in format "GHS:field=value",
                     e.g. "GHS:UC_NM_MN=Baltimore, or (even better; more specific)
                          "GHS:UC_NM_MN='Baltimore' and CTR_MN_NM=='United States'"
                    """
                )
        elif '.gpkg:' in area_data:
            gpkg = area_data.split(':')
            boundary_data = gpkg[0]
            query = gpkg[1]
        else:
            boundary_data = area_data
            query = ''

        command = (
            ' ogr2ogr -overwrite -progress -f "PostgreSQL" '
            f' PG:"host={db_host} port={db_port} dbname={db}'
            f' user={db_user} password={db_pwd}" '
            f' "{boundary_data}" '
            f' -lco geometry_name="geom" -lco precision=NO '
            f' -t_srs {crs_srid} -nln "study_region_boundary" '
            f' {query}'
        )
        print(command)
        failure = sp.call(command, shell=True)
        if failure == 1:
            sys.exit(
                f"Error reading in boundary data '{area_data}' (check format)",
            )
    except Exception as e:
        raise Exception(f'Error reading in boundary data (check format): {e}')

    print('\nCreate urban region boundary... ', end='', flush=True)
    if (
        area_data.startswith('GHS:')
        or not study_region_boundary['ghsl_urban_intersection']
    ):
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
            with engine.begin() as connection:
                connection.execute(text(sql))
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
        with engine.begin() as connection:
            result = connection.execute(text(sql))
            bbox = ' '.join(
                [str(coord) for coord in [coords for coords in result][0]],
            )

        command = (
            ' ogr2ogr -overwrite -progress -f "PostgreSQL" '
            f' PG:"host={db_host} port={db_port} dbname={db}'
            f' user={db_user} password={db_pwd}" '
            f' "{urban_region["data_dir"]}" '
            f' -lco geometry_name="geom" -lco precision=NO '
            f' -t_srs {crs_srid} -nln full_urban_region '
            f' -spat {bbox} -spat_srs {crs_srid} '
        )
        print(command)
        sp.call(command, shell=True)
        sql = f"""
           CREATE TABLE IF NOT EXISTS urban_region AS
           SELECT '{name}'::text AS "study_region",
                  '{db}'::text AS "db",
                  ST_Area(a.geom)/10^6 AS area_sqkm,
                  a.geom
           FROM full_urban_region a,
           "study_region_boundary" b
           WHERE ST_Intersects(a.geom,b.geom);
           CREATE INDEX IF NOT EXISTS urban_region_gix ON urban_region USING GIST (geom);
           CREATE TABLE IF NOT EXISTS urban_study_region AS
           SELECT b."study_region",
                  b."db",
                  ST_Area(ST_Union(ST_Intersection(a.geom,b.geom)))/10^6 AS area_sqkm,
                  ST_Union(ST_Intersection(a.geom,b.geom)) geom
           FROM "study_region_boundary" a,
                urban_region b
           GROUP BY b."study_region_boundary", b."db";
           CREATE INDEX IF NOT EXISTS urban_study_region_gix ON urban_study_region USING GIST (geom);
           """
        with engine.begin() as connection:
            connection.execute(text(sql))
        print('Done.')

    print(
        f'\nCreate {study_buffer} m buffered study region... ',
        end='',
        flush=True,
    ),
    study_buffer_km = study_buffer / 1000
    buffered_urban_study_region_extent = f'{study_buffer_km} km'
    sql = f"""
    CREATE TABLE IF NOT EXISTS {buffered_urban_study_region} AS
          SELECT "study_region",
                 db,
                 '{buffered_urban_study_region_extent}'::text AS "Study region buffer",
                 ST_Buffer(geom,{study_buffer}) AS geom
            FROM  urban_study_region ;
    CREATE INDEX IF NOT EXISTS {buffered_urban_study_region}_gix ON
        {buffered_urban_study_region} USING GIST (geom);
    """
    with engine.begin() as connection:
        connection.execute(text(sql))
    print('Done.')
    print(
        f"""\nThe following layers have been created:
    \n- study_region_boundary: To represent a policy-relevant administrative boundary (or proxy for this).
    \n- urban_region: Representing the urban area surrounding the study region.
    \n- urban_study_region: The urban portion of the policy-relevant study region.
    \n- {buffered_urban_study_region}: An analytical boundary extending {study_buffer} {units} further to mitigate edge effects.
    """,
    )

    if (
        db_contents.has_table('study_region_boundary')
        and db_contents.has_table('urban_region')
        and db_contents.has_table('urban_study_region')
        and db_contents.has_table(buffered_urban_study_region)
    ):
        return f"""Study region boundaries have previously been created (study_region_boundary, urban_region, urban_study_region and {buffered_urban_study_region}).   If you wish to recreate these, please manually drop them (e.g. using psql) or optionally drop the {db} database and start again (e.g. using the subprocesses/_drop_study_region_database.py utility script.\n"""
    else:
        raise Exception(
            """Study region boundary creation failed; check configuration and log files to identify specific issues.""",
        )

    # output to completion log
    script_running_log(script, task, start, codename)
    engine.dispose()


if __name__ == '__main__':
    main()
