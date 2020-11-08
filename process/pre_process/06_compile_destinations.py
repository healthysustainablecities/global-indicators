# Script:  compile_destinations.py
# Purpose: This script recompiles the destinations geodatabase:
#             - converts multi-point to point where req'd
#             - clips to study region
#             - restricts to relevant destinations
#             - removes redundant columns
#             - compile as a single feature.
#             - A point ID is comma-delimited in form "Destionation,OID"
#               - this is to facilitate output to csv file following OD matrix calculation
#
# Author:  Carl Higgs
# Date:    05/07/2018

import time
import psycopg2

from script_running_log import script_running_log

# Import custom variables for National Liveability indicator process
from _project_setup import *

# simple timer for log file
start = time.time()
script = os.path.basename(sys.argv[0])

# OUTPUT PROCESS
task = 'Compile study region destinations'
print("Commencing task: {} at {}".format(task,time.strftime("%Y%m%d-%H%M%S")))

# list destinations which have OpenStreetMap specified as their data source
df_osm_dest_unique = df_osm_dest[['dest_name','dest_full_name','domain']].drop_duplicates(subset=['dest_name'])
df_osm_dest['pre-condition'] = df_osm_dest['pre-condition'].replace('NULL','OR')
# dest_osm_list = [x.encode('utf') for x in df_osm_dest_unique['dest_name']]
# Create destination type table in sql database
# connect to the PostgreSQL server
conn = psycopg2.connect(dbname=db, user=db_user, password=db_pwd)
curs = conn.cursor()

# Create empty combined destination table
create_dest_type_table = '''
  DROP TABLE IF EXISTS dest_type;
  CREATE TABLE dest_type
  (
   dest_name varchar PRIMARY KEY,
   dest_name_full varchar,
   domain varchar NOT NULL,
   count integer
  );
   '''
curs.execute(create_dest_type_table)
conn.commit()

create_osm_destinations_table = '''
  DROP TABLE IF EXISTS osm_destinations CASCADE;
  CREATE TABLE osm_destinations
  (
   dest_oid SERIAL PRIMARY KEY,
   osm_id varchar,
   dest_name varchar NOT NULL,
   dest_name_full varchar NOT NULL,
   geom geometry(POINT)
  );
'''
curs.execute(create_osm_destinations_table)
conn.commit()

print("\nImporting destinations...")
print("\n{dest:50} {dest_count}".format(dest = "Destination",dest_count = "Import count"))
# for dest in dest_osm_list:
for row in df_osm_dest_unique.itertuples():
    dest = getattr(row,'dest_name')  
    dest_name_full = getattr(row,'dest_full_name')
    domain = getattr(row,'domain')
    dest_condition = []
    for condition in ['AND','OR','NOT']:
    # for condition in df_osm_dest[df_osm_dest['dest_name']==dest]['pre-condition'].unique():
        # print(condition)
        if condition == 'AND':
            clause = ' AND '.join(df_osm_dest[(df_osm_dest['dest_name']==dest)&(df_osm_dest['pre-condition']=='AND')].apply(lambda x: "{} IS NOT NULL".format(x.key) if x.value=='NULL' else "{} = '{}'".format(x.key,x.value),axis=1).values.tolist())
            dest_condition.append(clause)
        if condition == 'OR':
            clause = ' OR '.join(df_osm_dest[(df_osm_dest['dest_name']==dest)&(df_osm_dest['pre-condition']=='OR')].apply(lambda x: "{} IS NOT NULL".format(x.key) if x.value=='NULL' else "{} = '{}'".format(x.key,x.value),axis=1).values.tolist())
            dest_condition.append(clause)
        if condition != 'NOT':
            clause = ' AND '.join(df_osm_dest[(df_osm_dest['dest_name']==dest)&(df_osm_dest['pre-condition']=='NOT')].apply(lambda x: "{} IS NOT NULL".format(x.key) if x.value=='NULL' else "{} != '{}' OR access IS NULL".format(x.key,x.value),axis=1).values.tolist())
            dest_condition.append(clause)
    dest_condition = [x for x in dest_condition if x!='']
    # print(len(dest_condition))
    if len(dest_condition)==1:
        dest_condition = dest_condition[0]
    else:
        dest_condition = '({})'.format(') AND ('.join(dest_condition))
    print(dest_condition)
    combine__point_destinations = f'''
      INSERT INTO osm_destinations (osm_id, dest_name,dest_name_full,geom)
      SELECT osm_id, '{dest}','{dest_name_full}', d.geom 
        FROM {osm_prefix}_point d
       WHERE {dest_condition};
    '''
    curs.execute(combine__point_destinations)
    conn.commit()        
    
    # get point dest count in order to set correct auto-increment start value for polygon dest OIDs
    curs.execute(f'''SELECT count(*) FROM osm_destinations WHERE dest_name = '{dest}';''')
    dest_count = int(list(curs)[0][0])       
    
    combine_poly_destinations = f'''
      INSERT INTO osm_destinations (osm_id, dest_name,dest_name_full,geom)
      SELECT osm_id, '{dest}','{dest_name_full}', ST_Centroid(d.geom)
        FROM {osm_prefix}_polygon d
       WHERE {dest_condition};
    '''
    curs.execute(combine_poly_destinations)
    conn.commit()      
    
    curs.execute(f'''SELECT count(*) FROM osm_destinations WHERE dest_name = '{dest}';''')
    dest_count = int(list(curs)[0][0])  
    
    if dest_count > 0:
      summarise_dest_type = f'''
      INSERT INTO dest_type (dest_name,dest_name_full,domain,count)
      SELECT '{dest}',
             '{dest_name_full}',
             '{domain}',
             {dest_count}
      '''
      curs.execute(summarise_dest_type)
      conn.commit()
      # print destination name and tally which have been imported
      print(f"\n{dest:50} {dest_count:=10d}")
      print(f"({dest_condition})")


if str(custom_destinations) not in ['','nan']:
    import pandas as pd
    from sqlalchemy import create_engine
    engine = create_engine(f"postgresql://{db_user}:{db_pwd}@{db_host}/{db}")
    # bring in additional custom destinations, e.g. if OSM is not adequate
    custom_destinations = [x.strip() for x in custom_destinations.split(',')]
    file,dest_name,dest_name_full,lat,lon,epsg = custom_destinations
    df = pd.read_csv(f'{locale_dir}/{file}')
    df.to_sql('custom_destinations',engine,if_exists='replace')
    sql = f"""
    INSERT INTO osm_destinations (dest_name,dest_name_full,geom)
        SELECT {dest_name}::text dest_name,
               {dest_name_full}::text dest_name_full,
               ST_Transform(ST_SetSRID(ST_Point("{lon}"::float,"{lat}"::float),{epsg}),{srid}) geom 
        FROM custom_destinations;
    """
    curs.execute(sql)
    conn.commit()

create_osm_destinations_indices = '''
  CREATE INDEX osm_destinations_dest_name_idx ON osm_destinations (dest_name);
  CREATE INDEX osm_destinations_geom_geom_idx ON osm_destinations USING GIST (geom);
'''
curs.execute(create_osm_destinations_indices)
conn.commit()
curs.execute(grant_query)

# output to completion log    
script_running_log(script, task, start, locale)
conn.close()