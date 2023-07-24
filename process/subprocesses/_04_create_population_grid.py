"""
Create population grid.

Creates global virtual raster table files for Mollwiede and WGS84 GHS
population raster dataset tiles.
"""

import sys
import time

# Set up project and region parameters for GHSCIC analyses
import ghsci
import pandas as pd
from script_running_log import script_running_log
from sqlalchemy import text


def population_to_db(r):
    if r.config['population']['data_type'].startswith('raster'):
        # raster source
        r.raster_to_db(
            raster='population',
            config=r.config['population'],
            field='pop_est',
            reference_grid=True,
        )
    else:
        # vector source
        r.ogr_to_db(
            source=r.config['population']['data_dir'],
            layer=r.config['population_grid'],
            promote_to_multi=True,
            source_crs=f"{r.config['population']['crs_srid']}",
        )
        queries = [
            f"""ALTER TABLE {r.config["population_grid"]} ADD grid_id bigserial;""",
            f"""ALTER TABLE {r.config["population_grid"]} RENAME {r.config["population"]["vector_population_data_field"]} TO pop_est;""",
            f"""CREATE INDEX {r.config["population_grid"]}_ix  ON {r.config["population_grid"]} (grid_id);""",
        ]
        for sql in queries:
            with r.engine.begin() as connection:
                connection.execute(text(sql))
    print('Done.')


def derive_population_grid_variables(r):
    print(
        'Derive population grid variables and summaries... ',
        end='',
        flush=True,
    )
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
            # import data
            population_to_db(r)
            # derive variables
            derive_population_grid_variables(r)
            pop = r.get_df(r.config['population_grid'])
            pd.options.display.float_format = (
                lambda x: f'{x:.0f}' if int(x) == x else f'{x:,.1f}'
            )
            print('\nPopulation grid summary:')
            print(pop.describe().transpose())
            population_records = len(pop)
            population_sum = pop['pop_est'].sum()
            if (population_records > 0) and (population_sum > 0):
                # output to completion log
                script_running_log(r.config, script, task, start)
            else:
                sys.exit(
                    f'\nPopulation grid has length of {population_records} records and sum of population estimates {population_sum}.  Check population grid configuration details and source data before proceeding.',
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
