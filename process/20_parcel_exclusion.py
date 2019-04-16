# Script:  18_parcel_exclusion.py
# Purpose: This script develops a list of suspect parcels to investigate and exclude.
# Author:  Carl Higgs

import os
import sys
import time
import psycopg2
import subprocess as sp     # for executing external commands (e.g. pgsql2shp)
from sqlalchemy import create_engine

from script_running_log import script_running_log

# Import custom variables for National Liveability indicator process
from _project_setup import *

# simple timer for log file
start = time.time()
script = os.path.basename(sys.argv[0])
task = "Create list of excluded parcels"


# INPUT PARAMETERS
# output tables
# In this table {id} is not unique --- the idea is that jointly with indicator, {id} will be unique; such that we can see which if any parcels are missing multiple indicator values, and we can use this list to determine how many null values each indicator contains (ie. the number of {id}s for that indicator)
# The number of excluded parcels can be determined through selection of COUNT(DISTINCT({id}))
createTable_exclusions     = '''
  DROP TABLE IF EXISTS excluded_parcels;
  CREATE TABLE excluded_parcels
  ({id} varchar NOT NULL,
    geom geometry,
    indicator varchar NOT NULL,  
  PRIMARY KEY({id},indicator));
  '''.format(id = points_id.lower())

insert = "INSERT INTO excluded_parcels SELECT a.{id},a.geom, ".format(id = points_id.lower())
table = "\nFROM parcel_dwellings AS a \nLEFT JOIN "
match = " AS b \nON a.{id} = b.{id}  \nWHERE ".format(id = points_id.lower())
null = " IS NULL ON CONFLICT ({id},indicator) DO NOTHING ".format(id = points_id.lower())

# Island exceptions are defined using ABS constructs in the project configuration file.
# They identify contexts where null indicator values are expected to be legitimate due to true network isolation, 
# not connectivity errors.  
if island_exception not in ['','None']:
  print("\nIsland exception has been defined: {}".format(island_exception))
  island_exception = " a.gnaf_pid NOT IN (SELECT gnaf_pid FROM parcel_dwellings p LEFT JOIN abs_linkage s ON p.mb_code_20 = s.mb_code_2016 WHERE s.{island_exception}) AND ".format(island_exception=island_exception)
  island_reviewed = True
if island_exception =='':
  print("No island exceptions have been noted, but no note has been made in configuration file to indicator this region's network islands have been reviewed.\n If there are no exceptions for this study region, please enter 'None' in the project configuration file or have someone else do this for you.")
  island_reviewed = False
if island_exception == 'None':
  print("An analyst has reviewed this study region and determined that no island exceptions should be made\n(ie. all daily living indicator null values where they arise should lead to exclusion as they imply network connectivity failure)")
  island_exception = ''
  island_reviewed = True
# exclude on null indicator, and on null distance
query = '''
{insert} 'no network buffer'    {table} sausagebuffer_1600 {match} b.geom      {null};
{insert} 'null sc_nh1600m'      {table} sc_nh1600m         {match} sc_nh1600m  {null};
{insert} 'null dd_nh1600m'      {table} dd_nh1600m         {match} dd_nh1600m  {null};
{insert} 'null daily living'    {table} ind_daily_living   {match} {island_exception} dl_hard_1600m {null};
{insert} 'not urban parcel_sos' {table} parcel_sos         {match} sos_name_2016 NOT IN ('Major Urban','Other Urban');
{insert} 'no IRSD sa1_maincode' {table} abs_linkage ON a.mb_code_20 = abs_linkage.mb_code_2016 
    WHERE abs_linkage.sa1_maincode NOT IN (SELECT sa1_maincode FROM area_disadvantage)
    ON CONFLICT ({id},indicator) DO NOTHING;
'''.format(insert = insert, table = table, match = match, island_exception = island_exception, null = null, id = points_id.lower())

# OUTPUT PROCESS
print("\n{} for {}...".format(task,locale)),

conn = psycopg2.connect(database=db, user=db_user, password=db_pwd)
curs = conn.cursor()

curs.execute(createTable_exclusions)
conn.commit()

curs.execute(query)
conn.commit()
print("Done.")

summary_tables = '''
-- parcel summary
DROP TABLE IF EXISTS excluded_summary_parcels;
CREATE TABLE excluded_summary_parcels AS
SELECT gnaf_pid,
       geom
FROM parcel_dwellings
WHERE gnaf_pid IN (SELECT DISTINCT(gnaf_pid) gnaf_pid FROM excluded_parcels);

-- Mesh block summary
DROP TABLE IF EXISTS excluded_summary_mb;
CREATE TABLE excluded_summary_mb AS
SELECT
  p.mb_code_20 AS mb_code_2016,
  COUNT(b.gnaf_pid) AS excluded_parcels,
  COUNT(p.gnaf_pid) AS total_parcels,
  ROUND(COUNT(b.gnaf_pid)::numeric/COUNT(p.gnaf_pid)::numeric,2)  AS prop_excluded,
  a.mb_category_name_2016,
  a.dwelling             ,
  a.person               ,
  a.area_ha              ,
  a.geom
FROM parcel_dwellings p
LEFT JOIN abs_linkage a on p.mb_code_20 = a.mb_code_2016
LEFT JOIN excluded_summary_parcels b on p.gnaf_pid = b.gnaf_pid
GROUP BY p.mb_code_20,
         a.mb_category_name_2016,
         a.dwelling             ,
         a.person               ,
         a.area_ha              ,
         a.geom
ORDER BY p.mb_code_20;

-- SA1 summary
DROP TABLE IF EXISTS excluded_summary_sa1;
CREATE TABLE excluded_summary_sa1 AS
SELECT
  a.sa1_maincode,
  COUNT(b.gnaf_pid) AS excluded_parcels,
  COUNT(p.gnaf_pid) AS total_parcels,
  ROUND(COUNT(b.gnaf_pid)::numeric/COUNT(p.gnaf_pid)::numeric,2)  AS prop_excluded,
  SUM(a.dwelling) AS dwelling ,
  SUM(a.person) AS person,
  SUM(a.area_ha),
  s.geom
FROM parcel_dwellings p
LEFT JOIN abs_linkage a on p.mb_code_20 = a.mb_code_2016
LEFT JOIN excluded_summary_parcels b on p.gnaf_pid = b.gnaf_pid
LEFT JOIN main_sa1_2016_aust_full s ON a.sa1_maincode = s.sa1_mainco
GROUP BY a.sa1_maincode,s.geom
ORDER BY a.sa1_maincode;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO arc_sde;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO arc_sde;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO python;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO python;
'''
print("Create additional summary tables (parcel, mb, sa1) with geometries to explore exclusions spatially... "),
curs.execute(summary_tables)
conn.commit()
print("Done.")

engine = create_engine("postgresql://{user}:{pwd}@{host}/{db}".format(user = db_user,
                                                                 pwd  = db_pwd,
                                                                 host = db_host,
                                                                 db   = db))
                                                                 
print("\nExcluded parcels by reason for exclusion:")
summary = pandas.read_sql_query('''SELECT indicator, count(*) FROM excluded_parcels GROUP BY indicator;''',con=engine) 
print(summary)
                                                                 
print("\nExcluded parcels by section of state:")
summary = pandas.read_sql_query('''SELECT sos_name_2016, COUNT(DISTINCT(a.gnaf_pid)) from parcel_sos a LEFT JOIN excluded_parcels b ON a.gnaf_pid = b.gnaf_pid WHERE b.gnaf_pid IS NOT NULL GROUP BY sos_name_2016;''',con=engine) 
print(summary)

print("\nTotal excluded parcels:")
summary = pandas.read_sql_query('''SELECT COUNT(DISTINCT(gnaf_pid)) FROM excluded_parcels''',con=engine) 
print(summary['count'][0])

print("\nNetwork island diagnostics"),
if island_reviewed is False:
  print(" [study region *not yet flagged* as having been reviewed] ")
if island_reviewed is True:
  print(" [study region is flagged as having been reviewed] ")
print("(check table 'network_islands' to see if any large non-main network islands are legitimate islands;\nif so, they can be whitelisted in the project configuration file)\nSummary of network islands:")
network_islands = '''
--Create a geometry table for network island clusters 
DROP TABLE IF EXISTS network_islands; 
CREATE TABLE network_islands AS 
SELECT ST_Length(geom) AS length,  
       geom 
FROM (SELECT ST_SetSRID( 
           ST_CollectionHomogenize( 
             unnest(  
               ST_ClusterIntersecting( 
                 geom 
               ) 
             ) 
           ), 
           7845 
         ) AS geom FROM edges) t; 
         
--Grant permissions so we can open it in qgis and arcgis 
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO arc_sde; 
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO arc_sde; 
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO python; 
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO python; 
'''
curs.execute(network_islands)
conn.commit()

summary = pandas.read_sql_query('''
--Summarise length in descending order 
SELECT ROUND(length::numeric,0)::int AS length_metres from network_islands ORDER BY length DESC;  
''',con=engine) 
print(summary)

print('')
# output to completion log    
script_running_log(script, task, start, locale)

# clean up
conn.close()
