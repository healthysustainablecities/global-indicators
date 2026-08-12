"""Collate OpenStreetMap data for study region."""

import os
import subprocess as sp
import sys
import time
from datetime import datetime

# Set up project and region parameters for GHSCIC analyses
import ghsci
import psycopg2
from script_running_log import script_running_log


def create_poly_boundary_file(config):
    """Create poly file boundary from feature using ogr2poly script, for extracting OpenStreetMap region of interest."""
    db = config['db']
    db_host = config['db_host']
    db_port = config['db_port']
    db_user = config['db_user']
    db_pwd = config['db_pwd']
    feature = f"""PG:"dbname={db} host={db_host} port={db_port} user={db_user} password={db_pwd}" {config['buffered_urban_study_region']}"""
    print('Create poly file, using command: '),
    command = f'python /home/ghsci/process/subprocesses/ogr2poly.py {feature} -f "db"'
    print(command)
    sp.call(command, shell=True)
    command = f'mv {os.path.basename(config["codename_poly"])} {config["codename_poly"]}'
    print(f'\t{command}')
    sp.call(command, shell=True)
    print('Done.')


def extract_osm(config):
    """Extract OpenStreetMap for study region using poly boundary file."""
    print('Extract OSM for studyregion'),
    if os.path.isfile(config['OpenStreetMap']['osm_region']):
        print(
            f"""...\r\n.osm file "{config['OpenStreetMap']['osm_region']}" already exists""",
        )
    else:
        print(' using command:')
        command = f"""osmconvert "{config['OpenStreetMap']['data_dir']}" -B="{config['codename_poly']}" -o="{config['OpenStreetMap']['osm_region']}" """
        print(command)
        sp.call(command, shell=True)
    print('Done.')


def import_study_region_osm_to_db(r, ghsci):
    """Import buffered study region OpenStreetMap excerpt to spatial database."""
    db = r.config['db']
    db_host = r.config['db_host']
    db_port = r.config['db_port']
    db_user = r.config['db_user']
    db_pwd = r.config['db_pwd']
    conn = psycopg2.connect(
        database=db, user=db_user, password=db_pwd, host=db_host, port=db_port,
    )
    curs = conn.cursor()
    curs.execute(
        f"""SELECT 1 WHERE to_regclass('public.{r.config["osm_prefix"]}_line') IS NOT NULL;""",
    )
    res = curs.fetchone()
    if res is None:
        print('Copying OSM excerpt to pgsql...'),
        command = f"""osm2pgsql -U {db_user} -l -d {db} --host {db_host} --port {db_port} {r.config['OpenStreetMap']["osm_region"]} --hstore --prefix {r.config["osm_prefix"]} --log-progress=false"""
        print(command)
        sp.call(command, shell=True)
        print('Done.')

        for shape in ['line', 'point', 'polygon', 'roads']:
            # Define tags for which presence of values is suggestive of some kind of open space
            # These are defined in the _project_configuration worksheet 'open_space_defs' under the 'required_tags' column.
            required_tags = '\n'.join(
                [
                    (
                        f'ALTER TABLE {r.config["osm_prefix"]}_{shape} ADD COLUMN IF NOT EXISTS "{x}" varchar;'
                    )
                    for x in ghsci.osm_open_space['os_required']['criteria']
                ],
            )
            sql = [
                f"""
            -- Add geom column to polygon table, appropriately transformed to project spatial reference system
            ALTER TABLE {r.config["osm_prefix"]}_{shape} ADD COLUMN geom geometry;
            UPDATE {r.config["osm_prefix"]}_{shape} SET geom = ST_Transform(way,{r.config['crs']['srid']});
            CREATE INDEX {r.config["osm_prefix"]}_{shape}_idx ON {r.config["osm_prefix"]}_{shape} USING GIST (geom);
            """,
                f"""
            -- Add other columns which are important if they exists, but not important if they don't
            -- --- except that there presence is required for ease of accurate querying.
            {required_tags}""",
            ]
            for query in sql:
                query_start = time.time()
                print(f'\nExecuting: {query}')
                curs.execute(query)
                conn.commit()
                duration = (time.time() - query_start) / 60
                print(f'Executed in {duration} mins')

        curs.execute(ghsci.grant_query)
        conn.commit()
    else:
        print(
            'It appears that OSM data has already been imported for this region.',
        )
    conn.close()


def create_osm_resources(codename):
    """Collate OpenStreetMap data for study region."""
    start = time.time()
    script = '_02_create_osm_resources'
    task = 'create study region boundary'
    r = ghsci.Region(codename)

    create_poly_boundary_file(r.config)
    extract_osm(r.config)
    import_study_region_osm_to_db(r, ghsci)
    # output to completion log
    script_running_log(r.config, script, task, start)


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    create_osm_resources(codename)


if __name__ == '__main__':
    main()
