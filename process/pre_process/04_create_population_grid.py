"""
Create population grid.

Creates global virtual raster table files for Mollwiede and WGS84 GHS
population raster dataset tiles.
"""

import subprocess as sp
import time

import geopandas as gpd

# Set up project and region parameters for GHSCIC analyses
from _project_setup import *
from _utils import reproject_raster
from osgeo import gdal
from script_running_log import script_running_log
from sqlalchemy import create_engine, inspect
from tqdm import tqdm

# disable noisy GDAL logging
# gdal.SetConfigOption('CPL_LOG', 'NUL')  # Windows
gdal.SetConfigOption("CPL_LOG", "/dev/null")  # Linux/MacOS


def main():
    # simple timer for log file
    start = time.time()
    script = os.path.basename(sys.argv[0])
    task = "Create population grid excerpt for city"
    engine = create_engine(f"postgresql://{db_user}:{db_pwd}@{db_host}/{db}")
    db_contents = inspect(engine)

    # population raster set up
    population_stub = f"{locale_dir}/{population_grid}_{locale}"
    clipping_boundary = gpd.GeoDataFrame.from_postgis(
        f"""SELECT geom FROM {buffered_urban_study_region}""",
        engine,
        geom_col="geom",
    )

    # construct virtual raster table
    vrt = f'{population["data_dir"]}/{population_grid}_{population["crs"]}.vrt'
    population_raster_clipped = f'{population_stub}_{population["crs"]}.tif'
    population_raster_projected = f"{population_stub}_{srid}.tif"
    print("Global population dataset...", end="", flush=True)
    if not os.path.isfile(vrt):
        tif_folder = population["data_dir"]
        tif_files = [
            os.path.join(tif_folder, file)
            for file in os.listdir(tif_folder)
            if os.path.splitext(file)[-1] == ".tif"
        ]
        gdal.BuildVRT(vrt, tif_files)
        print(f"  has now been indexed ({vrt}).")
    else:
        print(f"  has already been indexed ({vrt}).")
    print("\nPopulation data clipped to region...", end="", flush=True)
    if not os.path.isfile(population_raster_clipped):
        # extract study region boundary in projection of tiles
        clipping = clipping_boundary.to_crs(population["crs"])
        # get clipping boundary values in required order for gdal translate
        bbox = list(
            clipping.bounds[["minx", "maxy", "maxx", "miny"]].values[0]
        )
        # bbox = list(clipping.bounds.values[0])
        gdal.Translate(population_raster_clipped, vrt, projWin=bbox)
        print(f"  has now been created ({population_raster_clipped}).")
    else:
        print(f"  has already been created ({population_raster_clipped}).")
    print("\nPopulation data projected for region...", end="", flush=True)
    if not os.path.isfile(population_raster_projected):
        # reproject and save the re-projected clipped raster
        # (see config file for reprojection function)
        reproject_raster(
            inpath=population_raster_clipped,
            outpath=population_raster_projected,
            new_crs=crs,
        )
        print(f"  has now been created ({population_raster_projected}).")
    else:
        print(f"  has already been created ({population_raster_projected}).")
    print(
        "\nPrepare population data grid for analysis (this may take a while)...",
        end="",
        flush=True,
    )
    # import raster to postgis and vectorise, as per http://www.brianmcgill.org/postgis_zonal.pdf
    command = (
        f"raster2pgsql -d -s {srid} -I -Y "
        f"-N {population['raster_nodata']} "
        f"-t  1x1 {population_raster_projected} {population_grid} "
        f"| PGPASSWORD={db_pwd} psql -U postgres -h {db_host} -d {db} "
        ">> /dev/null"
    )
    sp.call(command, shell=True)
    print("Done.")
    print("Derive population grid variables and summaries", end="", flush=True)
    queries = [
        f"""
    ALTER TABLE {population_grid} DROP COLUMN rid;
    ALTER TABLE {population_grid} ADD grid_id bigserial;
    ALTER TABLE {population_grid} ADD COLUMN IF NOT EXISTS pop_est int;
    ALTER TABLE {population_grid} ADD COLUMN IF NOT EXISTS area_sqkm float;
    ALTER TABLE {population_grid} ADD COLUMN IF NOT EXISTS pop_per_sqkm float;
    ALTER TABLE {population_grid} ADD COLUMN IF NOT EXISTS intersection_count int;
    ALTER TABLE {population_grid} ADD COLUMN IF NOT EXISTS intersections_per_sqkm float;
    ALTER TABLE {population_grid} ADD COLUMN IF NOT EXISTS geom geometry;
    """,
        f"""DELETE FROM {population_grid} WHERE (ST_SummaryStats(rast)).sum IS NULL;""",
        f"""UPDATE {population_grid} SET geom = ST_ConvexHull(rast);""",
        f"""CREATE INDEX {population_grid}_ix  ON {population_grid} (grid_id);""",
        f"""CREATE INDEX {population_grid}_gix ON {population_grid} USING GIST(geom);""",
        f"""
    DELETE FROM {population_grid}
        WHERE {population_grid}.grid_id NOT IN (
            SELECT p.grid_id
            FROM
                {population_grid} p,
                {buffered_urban_study_region} b
            WHERE ST_Intersects (
                p.geom,
                b.geom
            )
        );
    """,
        f"""UPDATE {population_grid} SET area_sqkm = ST_Area(geom)/10^6;""",
        f"""UPDATE {population_grid} SET pop_est = (ST_SummaryStats(rast)).sum;""",
        f"""UPDATE {population_grid} SET pop_per_sqkm = pop_est/area_sqkm;""",
        f"""ALTER TABLE {population_grid} DROP COLUMN rast;""",
        f"""
    CREATE MATERIALIZED VIEW pop_temp AS
    SELECT h."grid_id",
           COUNT(i.*) intersection_count
    FROM {population_grid} h
    LEFT JOIN {intersections_table} i
    ON st_contains(h.geom,i.geom)
    GROUP BY "grid_id";
    """,
        f"""
    UPDATE {population_grid} a
       SET intersection_count = b.intersection_count,
           intersections_per_sqkm = b.intersection_count/a.area_sqkm
      FROM pop_temp b
    WHERE a."grid_id" = b."grid_id";
    """,
        """DROP MATERIALIZED VIEW pop_temp;""",
        """
    ALTER TABLE urban_study_region ADD COLUMN IF NOT EXISTS area_sqkm double precision;
    ALTER TABLE urban_study_region ADD COLUMN IF NOT EXISTS pop_est int;
    ALTER TABLE urban_study_region ADD COLUMN IF NOT EXISTS pop_per_sqkm int;
    ALTER TABLE urban_study_region ADD COLUMN IF NOT EXISTS intersection_count int;
    ALTER TABLE urban_study_region ADD COLUMN IF NOT EXISTS intersections_per_sqkm double precision;
    """,
        f"""
    UPDATE urban_study_region a
        SET
            area_sqkm = b.area_sqkm,
            pop_est = b.pop_est,
            pop_per_sqkm = b.pop_est/b.area_sqkm,
            intersection_count = b.intersection_count,
            intersections_per_sqkm = b.intersection_count/b.area_sqkm
        FROM (
            SELECT
                "study_region",
                ST_Area(u.geom)/10^6 area_sqkm,
                SUM(p.pop_est) pop_est,
                SUM(p.intersection_count) intersection_count
            FROM urban_study_region u,
                 {population_grid} p
            WHERE ST_Intersects(u.geom,p.geom)
            GROUP BY u."study_region",u.geom
            ) b
        WHERE a.study_region = b.study_region;
    """,
    ]
    for sql in tqdm(queries):
        with engine.begin() as connection:
            connection.execute(sql)

    # grant access to the tables just created
    with engine.begin() as connection:
        connection.execute(grant_query)

    print("Done.")

    # output to completion log
    script_running_log(script, task, start, locale)
    engine.dispose()


if __name__ == "__main__":
    main()
