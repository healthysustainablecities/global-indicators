# Import OSM to a postgresql 
# Author:  Carl Higgs
# Date:    20180626


import subprocess as sp     # for executing external commands (e.g. pgsql2shp or ogr2ogr)
import time
import psycopg2
from script_running_log import script_running_log

# Import custom variables for National Liveability indicator process
from _project_setup import *

# simple timer for log file
start_beginning = time.time()
script = os.path.basename(sys.argv[0])
task = 'Import OSM'

# connect to the PostgreSQL server and ensure privileges are granted for all public tables
conn = psycopg2.connect(dbname=db, user=db_user, password=db_pwd)
curs = conn.cursor()  

# import buffered study region OSM excerpt to pgsql, 
print("Copying OSM excerpt to pgsql..."),
command = 'osm2pgsql -U {user} -l -d {db} {osm} --hstore --style {style} --prefix {prefix}'.format(user = db_user, 
                                                                               db = db,
                                                                               osm = osm_source,
                                                                               style = osm2pgsql_style,
                                                                               prefix = osm_prefix) 
print(command)
sp.call(command, shell=True, cwd=osm2pgsql_exe)                           
print("Done.")


print("Copy the network edges and nodes from gdb to postgis..."),
command = (
        ' ogr2ogr -overwrite -progress -f "PostgreSQL" ' 
        ' PG:"host={host} port=5432 dbname={db}'
        ' user={user} password = {pwd}" '
        ' {gdb} {feature} '
        ' -lco geometry_name="geom"'.format(host = db_host,
                                     db = db,
                                     user = db_user,
                                     pwd = db_pwd,
                                     gdb = gdb_path,
                                     feature = '"edges" "nodes"') 
        )
print(command)
sp.call(command, shell=True)
print("Done (although, if it didn't work you can use the printed command above to do it manually)")

# connect to the PostgreSQL server and ensure privileges are granted for all public tables
curs.execute(grant_query)
conn.commit()

required_fields_list = df_osm["required_tags"].dropna().tolist()

for shape in ['line','point','polygon','roads']:
  # Define tags for which presence of values is suggestive of some kind of open space 
  # These are defined in the _project_configuration worksheet 'open_space_defs' under the 'required_tags' column.
  required_tags = '\n'.join(['ALTER TABLE {prefix}_{shape} ADD COLUMN IF NOT EXISTS "{field}" varchar;'.format(prefix = osm_prefix,shape = shape, field = x.encode('utf')) for x in required_fields_list])

  sql = ['''
  -- Add geom column to polygon table, appropriately transformed to project spatial reference system
  ALTER TABLE {osm_prefix}_{shape} ADD COLUMN geom geometry; 
  UPDATE {osm_prefix}_{shape} SET geom = ST_Transform(way,{srid}); 
  CREATE INDEX {osm_prefix}_{shape}_idx ON {osm_prefix}_{shape} USING GIST (geom);
  '''.format(osm_prefix = osm_prefix, shape = shape,srid=srid),
  '''
  -- Add other columns which are important if they exists, but not important if they don't
  -- --- except that there presence is required for ease of accurate querying.
  {}'''.format(required_tags)]
  for query in sql:
    start = time.time()
    print("\nExecuting: {}".format(query))
    curs.execute(query)
    conn.commit()
    print("Executed in {} mins".format((time.time()-start)/60))

curs.execute(grant_query)
conn.commit()    
  
# output to completion log    
script_running_log(script, task, start_beginning, locale)
conn.close()
 