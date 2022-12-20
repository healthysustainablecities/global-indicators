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
from sqlalchemy import create_engine, inspect


def main():
    # simple timer for log file
    start = time.time()
    script = os.path.basename(sys.argv[0])
    task = "create study region boundary"

    engine = create_engine(f"postgresql://{db_user}:{db_pwd}@{db_host}/{db}")
    db_contents = inspect(engine)
    if (
        db_contents.has_table(study_region)
        and db_contents.has_table("urban_region")
        and db_contents.has_table("urban_study_region")
        and db_contents.has_table(buffered_urban_study_region)
    ):
        sys.exit(
            f"""Study region boundaries have previously been created ({study_region}, urban_region, urban_study_region and {buffered_urban_study_region}).   If you wish to recreate these, please manually drop them (e.g. using psql) or optionally drop the {db} database and start again (e.g. using the pre_process/_drop_study_region_database.py utility script.\n"""
        )
    print("Create study region boundary... ")
    # import study region policy-relevant administrative boundary, or GHS boundary
    try:
        if area_data.startswith("GHS:"):
            # Global Human Settlements urban area is used to define this study region
            boundary_data = urban_region["data_dir"]
            query = f""" -where "{area_data.replace('GHS:', '')}" """
            if "=" not in query:
                sys.exit(
                    """
                    A Global Human Settlements urban area was indicated for the study region,
                    however the query wasn't understood
                    (should be in format "GHS:field=value",
                     e.g. "GHS:UC_NM_MN=Baltimore, or (even better; more specific)
                          "GHS:UC_NM_MN='Manchester' and CTR_MN_NM=='United Kingdom'"
                    """
                )
        elif ".gpkg:" in area_data:
            gpkg = area_data.split(":")
            boundary_data = f"../{gpkg[0]}"
            query = gpkg[1]
        else:
            boundary_data = f"../{area_data}"
            query = ""

        command = (
            ' ogr2ogr -overwrite -progress -f "PostgreSQL" '
            f' PG:"host={db_host} port={db_port} dbname={db}'
            f' user={db_user} password={db_pwd}" '
            f' "{boundary_data}" '
            f' -lco geometry_name="geom" -lco precision=NO '
            f" -t_srs {crs} -nln {study_region} "
            f" {query}"
        )
        print(command)
        failure = sp.call(command, shell=True)
        if failure == 1:
            sys.exit(
                f"Error reading in boundary data '{area_data}' (check format)"
            )
    except Exception as e:
        sys.exit(f"Error reading in boundary data (check format): {e}")

    if area_data.startswith("GHS:") or not_urban_intersection in [
        True,
        "true",
        "True",
    ]:
        # e.g. Vic is not represented in the GHS data, so intersection is not used
        for table in ["urban_region", "urban_study_region"]:
            sql = f"""
                CREATE TABLE IF NOT EXISTS {table} AS
                SELECT '{full_locale}'::text AS "study_region",
                       '{db}'::text AS "db",
                       ST_Area(geom)/10^6 AS area_sqkm,
                       geom
                FROM {study_region};
                CREATE INDEX IF NOT EXISTS {table}_gix ON {table} USING GIST (geom);
                """
            with engine.begin() as connection:
                connection.execute(sql)
    else:
        # get study region bounding box to be used to retrieve intersecting urban geometries
        sql = f"""
            SELECT
                ST_Xmin(geom) xmin,
                ST_Ymin(geom) ymin,
                ST_Xmax(geom) xmax,
                ST_Ymax(geom) ymax
            FROM {study_region};
            """
        with engine.begin() as connection:
            bbox = connection.execute(sql)
        command = (
            ' ogr2ogr -overwrite -progress -f "PostgreSQL" '
            f' PG:"host={db_host} port={db_port} dbname={db}'
            f' user={db_user} password={db_pwd}" '
            f' {urban_region["data_dir"]} '
            f' -lco geometry_name="geom" -lco precision=NO '
            f" -t_srs {crs} -nln full_urban_region "
            f" -spat {bbox} -spat_srs {crs} "
        )
        print(command)
        sp.call(command, shell=True)
        sql = f"""
           CREATE TABLE IF NOT EXISTS urban_region AS
           SELECT '{full_locale}'::text AS "study_region",
                  '{db}'::text AS "db",
                  ST_Area(a.geom)/10^6 AS area_sqkm,
                  a.geom
           FROM full_urban_region a,
           {study_region} b
           WHERE ST_Intersects(a.geom,b.geom);
           DROP TABLE full_urban_region;
           CREATE INDEX IF NOT EXISTS urban_region_gix ON urban_region USING GIST (geom);
           CREATE TABLE IF NOT EXISTS urban_study_region AS
           SELECT b."study_region",
                  b."db",
                  ST_Area(ST_Union(ST_Intersection(a.geom,b.geom)))/10^6 AS area_sqkm,
                  ST_Union(ST_Intersection(a.geom,b.geom)) geom
           FROM {study_region} a,
                urban_region b
           GROUP BY b."study_region", b."db";
           CREATE INDEX IF NOT EXISTS urban_study_region_gix ON urban_study_region USING GIST (geom);
           """
        with engine.begin() as connection:
            connection.execute(sql)

    print(f"\nCreate {study_buffer} m buffered study region... "),
    study_buffer_km = study_buffer / 1000
    buffered_urban_study_region_extent = f"{study_buffer_km} km"
    sql = f"""
    CREATE TABLE IF NOT EXISTS {buffered_urban_study_region} AS
          SELECT "study_region",
                 db,
                 '{buffered_urban_study_region_extent}'::text AS "Study region buffer",
                 ST_Buffer(geom,{study_buffer}) AS geom
            FROM  urban_study_region ;
    CREATE INDEX IF NOT EXISTS {study_region}_{study_buffer}{units}_gix ON  {buffered_urban_study_region} USING GIST (geom);
    """
    with engine.begin() as connection:
        connection.execute(sql)

    print(
        f"""\nThe following layers have been created:
    \n- {study_region}: To represent a policy-relevant administrative boundary (or proxy for this).
    \n- urban_region: Representing the urban area surrounding the study region.
    \n- urban_study_region: The urban portion of the policy-relevant study region.
    \n- {buffered_urban_study_region}: An analytical boundary extending {study_buffer} {units} further to mitigate edge effects.
    """
    )

    # output to completion log
    script_running_log(script, task, start, locale)
    engine.dispose()


if __name__ == "__main__":
    main()
