"""
Remove study region database.

Commandline utility to drop a previously created database and advise to manually remove unwanted files.
"""

import getpass

import psycopg2

# Import project configuration file
from _project_setup import *
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def main():
    if codename in region_names:
        prompt = f'Dropping database {db}.  Please enter postgres password to confirm (see config.yml):'
        conn = psycopg2.connect(
            dbname=admin_db,
            user=admin_db,
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
                f"\nDatabase {db} has been dropped.\n\nManually remove any unwanted files for this study region from {region_dir.split('process')[1]}.\n",
            )
        else:
            print(
                'Database still appears to exist; check that it is not being accessed from any other programs (e.g. QGIS, psql, or another Python instance).\n',
            )
        conn.close()
    else:
        print(
            'Specified codename does not appear to be a configured region in regions.yml; please confirm your settings, or manually modify the database using psql.',
        )


if __name__ == '__main__':
    main()
