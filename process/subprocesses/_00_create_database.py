"""
Database creation.

Used to create database and related settings for creation of liveability
indicators.
"""
import sys
import time

# Import project configuration file
import ghsci
import psycopg2

# import getpass
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def create_database(codename):
    # simple timer for log file
    start = time.time()
    script = '_00_create_database'
    task = 'Create region-specific liveability indicator database and user'
    r = ghsci.Region(codename)
    print('Connecting to default database to action queries.')
    conn = psycopg2.connect(
        dbname=ghsci.settings['sql']['admin_db'],
        user=ghsci.settings['sql']['db_user'],
        password=ghsci.settings['sql']['db_pwd'],
        host=ghsci.settings['sql']['db_host'],
        port=ghsci.settings['sql']['db_port'],
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    curs = conn.cursor()

    # SQL queries
    create_database = f"""
    -- Create database
    CREATE DATABASE "{r.config['db']}"
    WITH OWNER = {ghsci.settings['sql']['db_user']}
    ENCODING = 'UTF8'
    TABLESPACE = pg_default
    CONNECTION LIMIT = -1
    TEMPLATE template0;
    """
    print(
        f'Creating database if not exists {r.config["db"]}... ',
        end='',
        flush=True,
    )
    curs.execute(
        f"""SELECT COUNT(*) = 0 FROM pg_catalog.pg_database WHERE datname = '{r.config["db"]}'""",
    )
    not_exists_row = curs.fetchone()
    not_exists = not_exists_row[0]
    if not_exists:
        curs.execute(create_database)
    print('Done.')

    comment_database = f"""
    COMMENT ON DATABASE "{r.config['db']}" IS '{r.config['dbComment']}';
    """
    print(
        f"""Adding comment "{r.config['dbComment']}"... """,
        end='',
        flush=True,
    )
    curs.execute(comment_database)
    print('Done.')

    create_user = f"""
    DO
    $do$
    BEGIN
       IF NOT EXISTS (
          SELECT
          FROM   pg_catalog.pg_roles
          WHERE  rolname = '{ghsci.settings["sql"]["db_user"]}') THEN

          CREATE ROLE {ghsci.settings["sql"]["db_user"]} LOGIN PASSWORD '{ghsci.settings["sql"]["db_pwd"]}';
       END IF;
    END
    $do$;
    """
    print(
        f'Creating user {ghsci.settings["sql"]["db_user"]}  if not exists... ',
        end='',
        flush=True,
    ),
    curs.execute(create_user)
    print('Done.')

    print(f'Connecting to {r.config["db"]}.', end='', flush=True)
    conn = psycopg2.connect(
        dbname=r.config['db'],
        user=ghsci.settings['sql']['db_user'],
        password=ghsci.settings['sql']['db_pwd'],
        host=ghsci.settings['sql']['db_host'],
        port=ghsci.settings['sql']['db_port'],
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    curs = conn.cursor()

    print('Creating required extensions ... ', end='', flush=True)
    create_extensions = f"""
    CREATE EXTENSION IF NOT EXISTS postgis;
    CREATE EXTENSION IF NOT EXISTS postgis_raster;
    ALTER DATABASE "{r.config['db']}" SET postgis.enable_outdb_rasters = true;
    ALTER DATABASE "{r.config['db']}" SET postgis.gdal_enabled_drivers TO 'ENABLE_ALL';
    CREATE EXTENSION IF NOT EXISTS postgis_sfcgal;
    CREATE EXTENSION IF NOT EXISTS pgrouting;
    SELECT postgis_full_version();
    CREATE EXTENSION IF NOT EXISTS hstore;
    CREATE EXTENSION IF NOT EXISTS tablefunc;
    """
    curs.execute(create_extensions)
    print('Done.')

    print('Creating threshold functions ... ', end='', flush=True)
    create_threshold_functions = """
    CREATE OR REPLACE FUNCTION threshold_hard(in int, in int, out int)
    RETURNS NULL ON NULL INPUT
    AS $$ SELECT ($1 < $2)::int $$
    LANGUAGE SQL;

    CREATE OR REPLACE FUNCTION threshold_soft(in int, in int, out double precision)
    RETURNS NULL ON NULL INPUT
    AS $$ SELECT 1 - 1/(1+exp(-{slope}*($1-$2)/($2::float))) $$
    LANGUAGE SQL;
    """.format(
        slope=ghsci.settings['network_analysis']['soft_threshold_slope'],
    )
    curs.execute(create_threshold_functions)
    print('Done.\n')

    curs.execute(ghsci.grant_query)

    # output to completion log
    from script_running_log import script_running_log

    script_running_log(script, task, start, codename)
    conn.close()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    create_database(codename)


if __name__ == '__main__':
    main()
