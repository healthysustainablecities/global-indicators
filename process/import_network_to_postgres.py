# Import network to postgresql
# Author:  Carl Higgs
# Date:    20190204


import subprocess as sp     # for executing external commands (e.g. pgsql2shp or ogr2ogr)
import time
import psycopg2
from script_running_log import script_running_log

# Import custom variables for National Liveability indicator process
from config_ntnl_li_process import *

# simple timer for log file
start = time.time()
script = os.path.basename(sys.argv[0])
task = 'Import network edges and nodes to postgresql'

# connect to the PostgreSQL server and ensure privileges are granted for all public tables
conn = psycopg2.connect(dbname=db, user=db_user, password=db_pwd)
curs = conn.cursor()  

print("Copy the network nodes and edges from gdb to postgis...")
for feature in ['edges','nodes']:
  command = (
          ' ogr2ogr -overwrite -progress -f "PostgreSQL" ' 
          ' PG:"host={host} port=5432 dbname={db}'
          ' user={user} password = {pwd}" '
          ' {gdb} "{feature}" '
          ' -lco geometry_name="geom"'.format(host = db_host,
                                       db = db,
                                       user = db_user,
                                       pwd = db_pwd,
                                       gdb = gdb_path,
                                       feature = feature) 
          )
  print(command)
  # sp.call(command, shell=True)
print("Done (although, if it didn't work you can use the printed command above to do it manually)")

# connect to the PostgreSQL server and ensure privileges are granted for all public tables
curs.execute(grant_query)
conn.commit()