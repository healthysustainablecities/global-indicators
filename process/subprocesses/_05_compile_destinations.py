"""
Compile destinations.

Collates destinations based on configuration settings from OpenStreetMap
data, with optional supplementation or replacement using custom
points_of_interest defined in the region configuration.
"""

import sys
import time

# Set up project and region parameters for GHSCIC analyses
import ghsci
from script_running_log import script_running_log
from sqlalchemy import text


def compile_osm_destinations(r, skip_dest_names=None):
    """Import destinations from OpenStreetMap point and polygon layers.

    Parameters
    ----------
    r : ghsci.Region
        Configured study region.
    skip_dest_names : set, optional
        dest_name keys to skip (e.g. those being replaced by
        points_of_interest with replace: true).
    """
    skip = skip_dest_names or set()
    df_osm_dest_unique = ghsci.df_osm_dest[
        ['dest_name', 'dest_full_name', 'domain']
    ].drop_duplicates(subset=['dest_name'])
    ghsci.df_osm_dest['pre-condition'] = ghsci.df_osm_dest[
        'pre-condition'
    ].replace('NULL', 'OR')
    for row in df_osm_dest_unique.itertuples():
        dest = getattr(row, 'dest_name')
        if dest in skip:
            continue
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


def compile_poi_destinations(r):
    """Import custom points_of_interest defined in the region configuration.

    Each key in r.config['points_of_interest'] must be a dest_name (e.g.
    'pt_any') matching a category used in configuration/indicators.yml.
    The spatial file is loaded via r.ogr_to_db (ogr2ogr), which reprojects
    to the study region CRS automatically.

    If replace: true, the OSM import for that dest_name is skipped entirely
    (handled in compile_destinations via skip_dest_names) and this function
    provides all rows for that category.

    If replace: false (default), custom rows are pooled with any OSM rows
    already imported, which is acceptable for distance-to-closest analyses.

    Metadata (dest_name_full, domain) is resolved in order:
      1. Lookup from ghsci.df_osm_dest if dest_name matches a known OSM key.
      2. Optional 'dest_name_full' / 'domain' fields in the YAML entry.
      3. Fallback: dest_name itself / 'Custom'.
    """
    poi_config = r.config.get('points_of_interest')
    if not isinstance(poi_config, dict):
        return

    print('\nImporting points_of_interest...')
    for dest_name, poi in poi_config.items():
        if not isinstance(poi, dict) or poi.get('data') is None:
            continue

        # Resolve dest_name_full and domain
        df_match = ghsci.df_osm_dest[
            ghsci.df_osm_dest['dest_name'] == dest_name
        ]
        if not df_match.empty:
            dest_name_full = df_match.iloc[0]['dest_full_name']
            domain = df_match.iloc[0]['domain']
        else:
            dest_name_full = poi.get('dest_name_full', dest_name)
            domain = poi.get('domain', 'Custom')

        tmp_layer = f'_poi_{dest_name}'

        # Load spatial data into a temporary PostgreSQL table
        r.ogr_to_db(source=poi['data'], layer=tmp_layer)

        # Insert point centroids into the destinations table
        insert_poi = f"""
          INSERT INTO destinations (dest_name, dest_name_full, geom)
          SELECT '{dest_name}', '{dest_name_full}', ST_Centroid(geom)
            FROM {tmp_layer};
        """
        with r.engine.begin() as connection:
            connection.execute(text(insert_poi))

        dest_count_sql = f"""SELECT count(*) FROM destinations WHERE dest_name = '{dest_name}';"""
        with r.engine.begin() as connection:
            dest_count = int(
                connection.execute(text(dest_count_sql)).first()[0],
            )

        if dest_count > 0:
            # Upsert dest_type: add to existing count if OSM rows were already
            # inserted (replace: false), or insert fresh (replace: true).
            upsert_dest_type = f"""
              INSERT INTO dest_type (dest_name, dest_name_full, domain, count)
              VALUES ('{dest_name}', '{dest_name_full}', '{domain}', {dest_count})
              ON CONFLICT (dest_name)
              DO UPDATE SET count = dest_type.count + EXCLUDED.count;
            """
            with r.engine.begin() as connection:
                connection.execute(text(upsert_dest_type))
            source_label = poi.get('source', poi['data'])
            print(f'\n{dest_name:50} {dest_count:=10d}')
            print(f'(source: {source_label})')

        # Drop the temporary staging table
        with r.engine.begin() as connection:
            connection.execute(text(f'DROP TABLE IF EXISTS {tmp_layer};'))


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

    # Determine which dest_name keys are fully replaced by points_of_interest
    poi_config = r.config.get('points_of_interest') or {}
    replace_dest_names = {
        k
        for k, v in poi_config.items()
        if isinstance(v, dict) and v.get('replace', False)
    }

    # Import OpenStreetMap destinations, skipping any replaced by custom data
    compile_osm_destinations(r, skip_dest_names=replace_dest_names)

    # Import custom points_of_interest (replace or pool with OSM, per config)
    compile_poi_destinations(r)

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
