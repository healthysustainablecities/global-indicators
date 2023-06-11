"""
Compile destinations.

Collates destinations based on configuration settings from OpenStreetMap
data.
"""

import sys
import time

# Set up project and region parameters for GHSCIC analyses
import ghsci
from script_running_log import script_running_log
from sqlalchemy import text


def custom_destination_setup(engine, r):
    import pandas as pd

    df = pd.read_csv(
        f'{r.config["region_dir"]}/{r.config["custom_destinations"]["file"]}',
    )
    df.to_sql('r.config["custom_destinations"]', engine, if_exists='replace')
    sql = f"""
    INSERT INTO destinations (dest_name,dest_name_full,geom)
        SELECT {r.config["custom_destinations"]["dest_name"]}::text dest_name,
                {r.config["custom_destinations"]["dest_name_full"]}::text dest_name_full,
                ST_Transform(ST_SetSRID(ST_Point(
                    "{r.config["custom_destinations"]["lon"]}"::float,
                    "{r.config["custom_destinations"]["lat"]}"::float),
                    {r.config["custom_destinations"]["epsg"]}),
                    {crs['srid']}
                    ) geom
        FROM r.config["custom_destinations"];
    """
    with engine.begin() as connection:
        connection.execute(text(sql))


def compile_destinations(codename):
    start = time.time()
    script = '_05_compile_destinations'
    task = 'Compile study region destinations'
    r = ghsci.Region(codename)
    # Create empty combined destination table
    create_dest_type_table = """
      DROP TABLE IF EXISTS dest_type;
      CREATE TABLE dest_type
      (
       dest_name varchar PRIMARY KEY,
       dest_name_full varchar,
       domain varchar NOT NULL,
       count integer
      );
       """
    with r.engine.begin() as connection:
        connection.execute(text(create_dest_type_table))

    create_destinations_table = """
      DROP TABLE IF EXISTS destinations CASCADE;
      CREATE TABLE destinations
      (
       dest_oid SERIAL PRIMARY KEY,
       osm_id varchar,
       dest_name varchar NOT NULL,
       dest_name_full varchar NOT NULL,
       geom geometry(POINT)
      );
    """
    with r.engine.begin() as connection:
        connection.execute(text(create_destinations_table))
    print('\nImporting destinations...')
    print(f'\n{"Destination":50} Import count')
    # list destinations which have OpenStreetMap specified as their data source
    df_osm_dest_unique = ghsci.df_osm_dest[
        ['dest_name', 'dest_full_name', 'domain']
    ].drop_duplicates(subset=['dest_name'])
    ghsci.df_osm_dest['pre-condition'] = ghsci.df_osm_dest[
        'pre-condition'
    ].replace('NULL', 'OR')
    # for dest in dest_osm_list:
    for row in df_osm_dest_unique.itertuples():
        dest = getattr(row, 'dest_name')
        dest_name_full = getattr(row, 'dest_full_name')
        domain = getattr(row, 'domain')
        dest_condition = []
        for condition in ['AND', 'OR', 'NOT']:
            if condition == 'AND':
                clause = ' AND '.join(
                    ghsci.df_osm_dest[
                        (ghsci.df_osm_dest['dest_name'] == dest)
                        & (ghsci.df_osm_dest['pre-condition'] == 'AND')
                    ]
                    .apply(
                        lambda x: f'{x.key} IS NOT NULL'
                        if x.value == 'NULL'
                        else f"{x.key} = '{x.value}'",
                        axis=1,
                    )
                    .values.tolist(),
                )
                dest_condition.append(clause)
            if condition == 'OR':
                clause = ' OR '.join(
                    ghsci.df_osm_dest[
                        (ghsci.df_osm_dest['dest_name'] == dest)
                        & (ghsci.df_osm_dest['pre-condition'] == 'OR')
                    ]
                    .apply(
                        lambda x: f'{x.key} IS NOT NULL'
                        if x.value == 'NULL'
                        else f"{x.key} = '{x.value}'",
                        axis=1,
                    )
                    .values.tolist(),
                )
                dest_condition.append(clause)
            if condition != 'NOT':
                clause = ' AND '.join(
                    ghsci.df_osm_dest[
                        (ghsci.df_osm_dest['dest_name'] == dest)
                        & (ghsci.df_osm_dest['pre-condition'] == 'NOT')
                    ]
                    .apply(
                        lambda x: f'{x.key} IS NOT NULL'
                        if x.value == 'NULL'
                        else f"{x.key} != '{x.value}' OR access IS NULL",
                        axis=1,
                    )
                    .values.tolist(),
                )
                dest_condition.append(clause)
        dest_condition = [x for x in dest_condition if x != '']
        if len(dest_condition) == 1:
            dest_condition = dest_condition[0]
        else:
            dest_condition = '({})'.format(') AND ('.join(dest_condition))
        print(dest_condition)
        combine__point_destinations = f"""
          INSERT INTO destinations (osm_id, dest_name,dest_name_full,geom)
          SELECT osm_id, '{dest}','{dest_name_full}', d.geom
            FROM {r.config["osm_prefix"]}_point d
           WHERE {dest_condition};
        """
        with r.engine.begin() as connection:
            connection.execute(text(combine__point_destinations))
        # get point dest count in order to set correct auto-increment start value for polygon dest OIDs
        dest_count_sql = f"""SELECT count(*) FROM destinations WHERE dest_name = '{dest}';"""
        with r.engine.begin() as connection:
            dest_count = int(
                connection.execute(text(dest_count_sql)).first()[0],
            )
        combine_poly_destinations = f"""
          INSERT INTO destinations (osm_id, dest_name,dest_name_full,geom)
          SELECT osm_id, '{dest}','{dest_name_full}', ST_Centroid(d.geom)
            FROM {r.config["osm_prefix"]}_polygon d
           WHERE {dest_condition};
        """
        with r.engine.begin() as connection:
            connection.execute(text(combine_poly_destinations))
        with r.engine.begin() as connection:
            dest_count = int(
                connection.execute(text(dest_count_sql)).first()[0],
            )
        if dest_count > 0:
            summarise_dest_type = f"""
            INSERT INTO dest_type (dest_name,dest_name_full,domain,count)
            SELECT '{dest}',
                    '{dest_name_full}',
                    '{domain}',
                    {dest_count}
            """
            with r.engine.begin() as connection:
                connection.execute(text(summarise_dest_type))
            # print destination name and tally which have been imported
            print(f'\n{dest:50} {dest_count:=10d}')
            print(f'({dest_condition})')

    if (
        'custom_destinations' in r.config
        and r.config['custom_destinations'] is not None
        and r.config['custom_destinations']['file'] is not None
    ):
        custom_destination_setup(engine, r)

    create_destinations_indices = """
      CREATE INDEX destinations_dest_name_idx ON destinations (dest_name);
      CREATE INDEX destinations_geom_geom_idx ON destinations USING GIST (geom);
    """
    with r.engine.begin() as connection:
        connection.execute(text(create_destinations_indices))

    # output to completion log
    script_running_log(r.config, script, task, start)
    r.engine.dispose()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    compile_destinations(codename)


if __name__ == '__main__':
    main()
