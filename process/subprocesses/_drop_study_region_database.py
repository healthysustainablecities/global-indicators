"""
Remove study region database.

Commandline utility to drop a previously created database and advise to manually remove unwanted files.
"""

import getpass
import sys

# Import project configuration file
import ghsci
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def drop_study_region_database(r):
    if type(r) == str:
        codename = r
        r = Region(codename)
    else:
        codename = r.codename
    db = r.config['db']
    admin_db = ghsci.settings['sql']['admin_db']
    db_host = r.config['db_host']
    db_port = r.config['db_port']
    db_user = r.config['db_user']
    r.engine.dispose()
    prompt = f'Dropping database {db}.  Please enter postgres password to confirm (see config.yml):'
    conn = psycopg2.connect(
        dbname=admin_db,
        user=db_user,
        password=getpass.getpass(prompt=f'{prompt}'),
        host=db_host,
        port=db_port,
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    curs = conn.cursor()
    drop_database = f"""DROP DATABASE IF EXISTS {db};"""
    curs.execute(drop_database)

    curs.execute(
        f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{db}'",
    )
    exists = curs.fetchone()
    if not exists:
        print(
            f"\nDatabase {db} has been dropped.\n\nManually remove any unwanted files for this study region from {r.config['region_dir'].split('process')[1]}.\n",
        )
    else:
        print(
            'Database still appears to exist; check that it is not being accessed from any other programs (e.g. QGIS, psql, or another Python instance).\n',
        )
    conn.close()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    r = Region(codename)
    r.drop()


if __name__ == '__main__':
    main()
