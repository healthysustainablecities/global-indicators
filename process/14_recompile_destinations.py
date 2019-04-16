# Script:  recompile_destinations_gdb.py
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
# Compile restricted gdb of destination features
task = 'Recompile destinations from {} to study region gdb as combined feature {}'.format(dest_gdb,os.path.join(gdb,study_destinations))
print("Commencing task: {} at {}".format(task,time.strftime("%Y%m%d-%H%M%S")))

# check that all destination names are unique; if not we'll have problems:
if df_destinations.destination.is_unique is not True:
  sys.exit("Destination names in 'destinations' tab of _project_configuration.xlsx are not unique, but they should be.  Please fix this, push the change to all users alerting them to the issue, and try again.");

### New idea for processing in PostGIS
# list features for which we appear to have data
# pre-processed destinations
dest_processed_list =  sp.check_output('ogrinfo {}'.format(src_destinations)).split('\r\n')
dest_processed_list = [x[(x.find(' ')+1):x.find(' (Point)')] for x in dest_processed_list[ dest_processed_list.index(''.join([x for x in dest_processed_list if x.startswith('1:')])):-1]]

# list destinations which have OpenStreetMap specified as their data source
dest_osm_list = [x.encode('utf') for x in df_osm_dest.dest_name.unique().tolist()]

print("\nCopy all pre-processed destinations to postgis..."),
command = (
        ' ogr2ogr -overwrite -progress -f "PostgreSQL" ' 
        ' PG:"host={host} port=5432 dbname={db}'
        ' user={user} password = {pwd}" '
        ' {gdb} '
        ' -lco geometry_name="geom"'.format(host = db_host,
                                     db = db,
                                     user = db_user,
                                     pwd = db_pwd,
                                     gdb = src_destinations) 
        )
print(command)
sp.call(command, shell=True)
print("Done (although, if it didn't work you can use the printed command above to do it manually)")

# Create destination type table in sql database
# connect to the PostgreSQL server
conn = psycopg2.connect(dbname=db, user=db_user, password=db_pwd)
curs = conn.cursor()

# Create empty combined destination table
create_dest_type_table = '''
  DROP TABLE IF EXISTS dest_type;
  CREATE TABLE dest_type
  (dest_class varchar NOT NULL,
   dest_name varchar PRIMARY KEY,
   dest_name_full varchar,
   domain varchar NOT NULL,
   count integer,
   cutoff_closest integer,
   cutoff_count integer);
   '''
curs.execute(create_dest_type_table)
conn.commit()

create_study_destinations_table = '''
  DROP TABLE IF EXISTS study_destinations;
  CREATE TABLE study_destinations
  (dest_oid varchar NOT NULL PRIMARY KEY,
   orig_id bigint,
   dest_class varchar NOT NULL,
   dest_name varchar NOT NULL,
   geom geometry(POINT));
  CREATE INDEX study_destinations_dest_name_idx ON study_destinations (dest_name);
  CREATE INDEX study_destinations_geom_geom_idx ON study_destinations USING GIST (geom);
'''
curs.execute(create_study_destinations_table)
conn.commit()

print("\nImporting destinations...")
print("\n{dest:50} {dest_count}".format(dest = "Destination",dest_count = "Import count"))
for dest in destination_list:
  dest_fields = {}
  for field in ['destination_class','dest_name_full','domain','cutoff_closest','cutoff_count']:
    dest_fields[field] = df_destinations.loc[df_destinations['destination'] == dest][field].to_string(index = False).encode('utf')
  if dest in dest_processed_list:
    # Ingest pre-processed destinations
    limit_extent = '''
      DELETE 
        FROM {dest} d 
       USING {buffered_study_region} b
       WHERE NOT ST_Intersects(d.geom,b.geom);
    '''.format(dest = dest,buffered_study_region = buffered_study_region)
    curs.execute(limit_extent)
    conn.commit()
    # count destinations matching this class already processed within the study region
    curs.execute('''SELECT count(*) FROM study_destinations WHERE dest_class = '{dest_class}';'''.format(dest = dest, dest_class = dest_fields['destination_class']))
    existing_dest_count = int(list(curs)[0][0])         
    # count destinations from this source within the study region
    curs.execute('''SELECT count(*) FROM {dest};'''.format(dest = dest))
    dest_count = int(list(curs)[0][0])     
    if dest_count==0:
        curs.execute('''DROP TABLE {dest}'''.format(dest = dest))
    elif dest_count > 0:
        # make sure all geom are point
        enforce_point = '''
          UPDATE {dest} 
             SET geom = ST_Centroid(geom)
           WHERE ST_GeometryType(geom) != 'ST_Point';
        '''.format(dest = dest)
        curs.execute(enforce_point)
        conn.commit()
        
        # get primary key, this would ideally be 'objectid', but we can't assume
        get_primary_key_field = '''
          SELECT a.attname
          FROM   pg_index i
          JOIN   pg_attribute a ON a.attrelid = i.indrelid
                               AND a.attnum = ANY(i.indkey)
          WHERE  i.indrelid = '{dest}'::regclass
          AND    i.indisprimary;
        '''.format(dest = dest)
        curs.execute(get_primary_key_field)
        dest_pkey = list(curs)[0][0]
        
        # it is possible that dest_class is not unique hence, the dest_oid will not be unique
        # unless we ensure it reflects a cumulative running index over previous and current dests
        # within class
        combine_destinations = '''
          INSERT INTO study_destinations (dest_oid,orig_id,dest_class,dest_name,geom)
          SELECT '{dest_class},' || {existing_dest_count} + ROW_NUMBER() OVER (ORDER BY {dest_pkey}), d.{dest_pkey},'{dest_class}', '{dest}', d.geom FROM {dest} d;
        '''.format(dest_class = dest_fields['destination_class'],
                   existing_dest_count = existing_dest_count,
                   dest_pkey = dest_pkey,
                   dest = dest)
        curs.execute(combine_destinations)
        conn.commit()
        
        summarise_dest_type = '''
        INSERT INTO dest_type (dest_class,dest_name,dest_name_full,domain,count,cutoff_closest,cutoff_count)
        SELECT '{dest_class}',
               '{dest}',
               '{dest_name_full}',
               '{domain}',
               {dest_count},
               {cutoff_closest},
               {cutoff_count}
        '''.format(dest_class     = dest_fields['destination_class'],
                   dest           = dest,
                   dest_name_full = dest_fields['dest_name_full'],
                   domain         = dest_fields['domain'],
                   dest_count     = dest_count,
                   cutoff_closest = dest_fields['cutoff_closest'],
                   cutoff_count   = dest_fields['cutoff_count'])
        curs.execute(summarise_dest_type)
        conn.commit()
        # print destination name and tally which have been imported
        print("{dest:50} {dest_count:=10d}".format(dest = dest,dest_count = dest_count))
        
  elif dest in dest_osm_list:
    dest_condition = ' OR '.join(df_osm_dest[df_osm_dest['dest_name']==dest].apply(lambda x: "{} IS NOT NULL".format(x.key) if x.value=='NULL' else "{} = '{}'".format(x.key,x.value),axis=1).tolist())
    combine__point_destinations = '''
      INSERT INTO study_destinations (dest_oid,orig_id, dest_class,dest_name,geom)
      SELECT '{dest_class},' || ROW_NUMBER() OVER (ORDER BY osm_id), osm_id, '{dest_class}', '{dest}', d.geom 
        FROM {osm_prefix}_point d
       WHERE {dest_condition};
    '''.format(dest_class = dest_fields['destination_class'],
               dest_pkey = dest_pkey,
               dest = dest,
               osm_prefix = osm_prefix,
               dest_condition = dest_condition)
    curs.execute(combine__point_destinations)
    conn.commit()        
    
    # get point dest count in order to set correct auto-increment start value for polygon dest OIDs
    curs.execute('''SELECT count(*) FROM study_destinations WHERE dest_name = '{dest}';'''.format(dest = dest))
    dest_count = int(list(curs)[0][0])       
    
    combine_poly_destinations = '''
      INSERT INTO study_destinations (dest_oid,orig_id, dest_class,dest_name,geom)
      SELECT '{dest_class},' || {dest_count} + ROW_NUMBER() OVER (ORDER BY osm_id), osm_id, '{dest_class}','{dest}', ST_Centroid(d.geom)
        FROM {osm_prefix}_polygon d
       WHERE {dest_condition};
    '''.format(dest_class = dest_fields['destination_class'],
               dest_count = dest_count,
               dest_pkey = dest_pkey,
               dest = dest,
               osm_prefix = osm_prefix,
               dest_condition = dest_condition)
    curs.execute(combine_poly_destinations)
    conn.commit()      
    
    curs.execute('''SELECT count(*) FROM study_destinations WHERE dest_name = '{dest}';'''.format(dest = dest))
    dest_count = int(list(curs)[0][0])  
    
    if dest_count > 0:
      summarise_dest_type = '''
      INSERT INTO dest_type (dest_class,dest_name,dest_name_full,domain,count,cutoff_closest,cutoff_count)
      SELECT '{dest_class}',
             '{dest}',
             '{dest_name_full}',
             '{domain}',
             {dest_count},
             {cutoff_closest},
             {cutoff_count}
      '''.format(dest_class     = dest_fields['destination_class'],
                 dest           = dest,
                 dest_name_full = dest_fields['dest_name_full'],
                 domain         = dest_fields['domain'],
                 dest_count     = dest_count,
                 cutoff_closest = dest_fields['cutoff_closest'],
                 cutoff_count   = dest_fields['cutoff_count'])
      curs.execute(summarise_dest_type)
      conn.commit()
      # print destination name and tally which have been imported
      print("\n{dest:50} {dest_count:=10d}".format(dest=dest,dest_count=dest_count))
      print("({dest_condition})".format(dest_condition=dest_condition))
  else:
    print("No data appears to be stored for destination {}.".format(dest))

# Copy study region destination table from PostgreSQL db to ArcGIS gdb
print("Copy study destinations to ArcGIS gdb... "),
curs.execute(grant_query)
conn.commit()
arcpy.env.workspace = db_sde_path
arcpy.env.overwriteOutput = True 
arcpy.CopyFeatures_management('public.study_destinations', os.path.join(gdb_path,'study_destinations')) 
print("Done.")


# When destinations are imported for study region, we don't want to retain all of these; now, purgefor dest in purge_dest_list:
for dest in purge_dest_list:
   sql = "DROP TABLE IF EXISTS {}".format(dest)
   curs.execute(sql)
   conn.commit()

# output to completion log    
script_running_log(script, task, start, locale)
conn.close()