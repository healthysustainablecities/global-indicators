"""
Create population grid.

Creates global virtual raster table files for Mollwiede and WGS84 GHS
population raster dataset tiles.
"""

import os
import subprocess as sp
import sys
import time

# Set up project and region parameters for GHSCIC analyses
import ghsci
import pandas as pd
from osgeo import gdal
from script_running_log import script_running_log
from sqlalchemy import create_engine, inspect, text

# disable noisy GDAL logging
# gdal.SetConfigOption('CPL_LOG', 'NUL')  # Windows
gdal.SetConfigOption('CPL_LOG', '/dev/null')  # Linux/MacOS


def reproject_raster(inpath, outpath, new_crs):
    import rasterio
    from rasterio.warp import (
        Resampling,
        calculate_default_transform,
        reproject,
    )

    dst_crs = new_crs  # CRS for web meractor
    with rasterio.open(inpath) as src:
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds,
        )
        kwargs = src.meta.copy()
        kwargs.update(
            {
                'crs': dst_crs,
                'transform': transform,
                'width': width,
                'height': height,
            },
        )
        with rasterio.open(outpath, 'w', **kwargs) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=dst_crs,
                    resampling=Resampling.nearest,
                )


def extract_population_from_raster(r):
    print('Extracting population raster data...')
    db = r.config['db']
    db_host = r.config['db_host']
    db_pwd = r.config['db_pwd']
    population_stub = (
        f'{r.config["region_dir"]}/{r.config["population_grid"]}_{r.codename}'
    )
    # construct virtual raster table
    vrt = f'{r.config["population"]["data_dir"]}/{r.config["population_grid"]}_{r.config["population"]["crs_srid"]}.vrt'
    population_raster_clipped = (
        f'{population_stub}_{r.config["population"]["crs_srid"]}.tif'
    )
    population_raster_projected = (
        f'{population_stub}_{r.config["crs"]["srid"]}.tif'
    )
    print('Raster population dataset...', end='', flush=True)
    if not os.path.isfile(vrt):
        tif_folder = f'{r.config["population"]["data_dir"]}'
        tif_files = [
            os.path.join(tif_folder, file)
            for file in os.listdir(tif_folder)
            if os.path.splitext(file)[-1] == '.tif'
        ]
        gdal.BuildVRT(vrt, tif_files)
        print(f'  has now been indexed ({vrt}).')
    else:
        print(f'  has already been indexed ({vrt}).')
    print('\nPopulation data clipped to region...', end='', flush=True)
    if not os.path.isfile(population_raster_clipped):
        # extract study region boundary in projection of tiles
        clipping_query = (
            f'SELECT geom FROM {r.config["buffered_urban_study_region"]}'
        )
        clipping = r.get_gdf(text(clipping_query), geom_col='geom').to_crs(
            r.config['population']['crs_srid'],
        )
        # get clipping boundary values in required order for gdal translate
        bbox = list(
            clipping.bounds[['minx', 'maxy', 'maxx', 'miny']].values[0],
        )
        # bbox = list(clipping.bounds.values[0])
        gdal.Translate(population_raster_clipped, vrt, projWin=bbox)
        print(f'  has now been created ({population_raster_clipped}).')
    else:
        print(f'  has already been created ({population_raster_clipped}).')
    print('\nPopulation data projected for region...', end='', flush=True)
    if not os.path.isfile(population_raster_projected):
        # reproject and save the re-projected clipped raster
        # (see config file for reprojection function)
        reproject_raster(
            inpath=population_raster_clipped,
            outpath=population_raster_projected,
            new_crs=r.config['crs']['srid'],
        )
        print(f'  has now been created ({population_raster_projected}).')
    else:
        print(f'  has already been created ({population_raster_projected}).')
    if r.config['population_grid'] not in r.tables:
        print(
            f'\nImport population grid {r.config["population_grid"]} to database... ',
            end='',
            flush=True,
        )
        # import raster to postgis and vectorise, as per http://www.brianmcgill.org/postgis_zonal.pdf
        command = (
            f'raster2pgsql -d -s {r.config["crs"]["srid"]} -I -Y '
            f"-N {r.config['population']['raster_nodata']} "
            f'-t  1x1 {population_raster_projected} {r.config["population_grid"]} '
            f'| PGPASSWORD={db_pwd} psql -U postgres -h {db_host} -d {db} '
            '>> /dev/null'
        )
        sp.call(command, shell=True)
        print('Done.')
    else:
        print(f'{r.config["population_grid"]} has been imported to database.')


def raster_sql_processing(r):
    queries = [
        f"""ALTER TABLE {r.config["population_grid"]} DROP COLUMN rid;""",
        f"""DELETE FROM {r.config["population_grid"]} WHERE (ST_SummaryStats(rast)).sum IS NULL;""",
        f"""ALTER TABLE {r.config["population_grid"]} ADD grid_id bigserial;""",
        f"""ALTER TABLE {r.config["population_grid"]} ADD COLUMN IF NOT EXISTS pop_est int;""",
        f"""ALTER TABLE {r.config["population_grid"]} ADD COLUMN IF NOT EXISTS geom geometry;""",
        f"""UPDATE {r.config["population_grid"]} SET geom = ST_ConvexHull(rast);""",
        f"""CREATE INDEX {r.config["population_grid"]}_ix  ON {r.config["population_grid"]} (grid_id);""",
        f"""CREATE INDEX {r.config["population_grid"]}_gix ON {r.config["population_grid"]} USING GIST(geom);""",
        f"""UPDATE {r.config["population_grid"]} SET pop_est = (ST_SummaryStats(rast)).sum;""",
        f"""ALTER TABLE {r.config["population_grid"]} DROP COLUMN rast;""",
    ]
    for sql in queries:
        with r.engine.begin() as connection:
            connection.execute(text(sql))


def extract_population_from_vector(r):
    print('Extracting population vector data...')
    db = r.config['db']
    db_host = r.config['db_host']
    db_port = r.config['db_port']
    db_user = r.config['db_user']
    db_pwd = r.config['db_pwd']
    population_data = r.config['population']['data_dir']
    if '.gpkg:' in population_data:
        gpkg = population_data.split(':')
        population_data = gpkg[0]
        query = gpkg[1]
    else:
        query = ''
    command = (
        ' ogr2ogr -overwrite -progress -f "PostgreSQL" '
        f' PG:"host={db_host} port={db_port} dbname={db}'
        f' user={db_user} password={db_pwd}" '
        f' "{population_data}" '
        f' -lco geometry_name="geom" -lco precision=NO '
        f' -t_srs {r.config["crs_srid"]} -nln "{r.config["population_grid"]}" '
        f' -nlt PROMOTE_TO_MULTI'
        f' {query}'
    )
    print(command)
    failure = sp.call(command, shell=True)
    if failure == 1:
        sys.exit(
            f"Error reading in population data '{population_data}' (check format)",
        )
    # except Exception as e:
    #     raise Exception(f'Error reading in boundary data (check format): {e}')
    print('Done.')


def vector_sql_processing(r):
    queries = [
        f"""ALTER TABLE {r.config["population_grid"]} ADD grid_id bigserial;""",
        f"""ALTER TABLE {r.config["population_grid"]} RENAME {r.config["population"]["vector_population_data_field"]} TO pop_est;""",
    ]
    for sql in queries:
        with r.engine.begin() as connection:
            connection.execute(text(sql))


def derive_population_grid_variables(r):
    print(
        'Derive population grid variables and summaries... ',
        end='',
        flush=True,
    )
    if r.config['population']['data_type'].startswith('vector'):
        vector_sql_processing(r)
    else:
        raster_sql_processing(r)
    queries = [
        f"""ALTER TABLE {r.config["population_grid"]} ADD COLUMN IF NOT EXISTS area_sqkm float;""",
        f"""ALTER TABLE {r.config["population_grid"]} ADD COLUMN IF NOT EXISTS pop_per_sqkm float;""",
        f"""ALTER TABLE {r.config["population_grid"]} ADD COLUMN IF NOT EXISTS intersection_count int;""",
        f"""ALTER TABLE {r.config["population_grid"]} ADD COLUMN IF NOT EXISTS intersections_per_sqkm float;""",
        f"""
    DELETE FROM {r.config["population_grid"]}
        WHERE {r.config["population_grid"]}.grid_id NOT IN (
            SELECT p.grid_id
            FROM
                {r.config["population_grid"]} p,
                {r.config["buffered_urban_study_region"]} b
            WHERE ST_Intersects (
                p.geom,
                b.geom
            )
        );
    """,
        f"""UPDATE {r.config["population_grid"]} SET area_sqkm = ST_Area(geom)/10^6;""",
        f"""UPDATE {r.config["population_grid"]} SET pop_per_sqkm = {r.config["population"]["population_denominator"]}/area_sqkm;""",
        f"""
    CREATE MATERIALIZED VIEW pop_temp AS
    SELECT h."grid_id",
            COUNT(i.*) intersection_count
    FROM {r.config["population_grid"]} h
    LEFT JOIN {r.config["intersections_table"]} i
    ON st_contains(h.geom,i.geom)
    GROUP BY "grid_id";
    """,
        f"""
    UPDATE {r.config["population_grid"]} a
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
            pop_per_sqkm = b.pop_denominator/b.area_sqkm,
            intersection_count = b.intersection_count,
            intersections_per_sqkm = b.intersection_count/b.area_sqkm
        FROM (
            SELECT
                "study_region",
                ST_Area(u.geom)/10^6 area_sqkm,
                SUM(p.{r.config['population']['population_denominator']}) pop_denominator,
                SUM(p.pop_est) pop_est,
                SUM(p.intersection_count) intersection_count
            FROM urban_study_region u,
                    {r.config['population_grid']} p
            WHERE ST_Intersects(u.geom,p.geom)
            GROUP BY u."study_region",u.geom
            ) b
        WHERE a.study_region = b.study_region;
    """,
    ]
    for sql in queries:
        with r.engine.begin() as connection:
            connection.execute(text(sql))
    print('Done.')


def create_population_grid(codename):
    # simple timer for log file
    start = time.time()
    script = '_04_create_population_grid'
    task = 'Create population grid excerpt for city'
    try:
        r = ghsci.Region(codename)
        tables = r.tables
        if r.config['population_grid'] in tables:
            print('Population grid already exists in database.')
        else:
            # population raster set up
            if r.config['population']['data_type'].startswith('vector'):
                extract_population_from_vector(r)
            else:
                extract_population_from_raster(r)
            derive_population_grid_variables(r)
            pop = r.get_df(r.config['population_grid'])
            pd.options.display.float_format = (
                lambda x: f'{x:.0f}' if int(x) == x else f'{x:,.1f}'
            )
            print('\nPopulation grid summary:')
            print(pop.describe().transpose())
            population_records_check = len(pop) > 0
            population_sum_check = (
                sum(pop[r.config['population_grid_field']]) > 0
            )
            if population_records_check and population_sum_check:
                # output to completion log
                script_running_log(r.config, script, task, start)
            else:
                sys.exit(
                    f'\nPopulation grid has length of {len(pop)} records and sum of population estimates {sum(pop[r.config["population_grid_field"]])}.  Check population grid configuration details and source data before proceeding.',
                )
    except Exception as e:
        sys.exit(f'Error: {e}')
    finally:
        r.engine.dispose()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    create_population_grid(codename)


if __name__ == '__main__':
    main()
