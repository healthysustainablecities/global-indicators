# Script:  meshblockDwellings.py
# Purpose: Project meshblock shapefile to correct spatial reference, join w/ dwelling data, crop to study region area
# Author:  Carl Higgs
# Date:    20180606

import psycopg2 
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
task = 'Project meshblock shapefile to correct spatial reference; join w/ dwelling data; and crop to Metro Urban area'

# ArcGIS environment settings
arcpy.env.workspace = gdb_path  
# create project specific folder in temp dir for scratch.gdb, if not exists
if not os.path.exists(os.path.join(temp,db)):
    os.makedirs(os.path.join(temp,db))
    
arcpy.env.scratchWorkspace = os.path.join(temp,db)  
arcpy.env.overwriteOutput = True 

# Define spatial reference
SpatialRef = arcpy.SpatialReference(SpatialRef)

# make feature layer and index  
arcpy.MakeFeatureLayer_management(meshblocks, 'layer')
arcpy.SelectLayerByLocation_management ('layer', select_features = buffered_study_region )

# copy study region meshblocks to gdb
arcpy.CopyFeatures_management('layer','meshblocks')

print("Copy meshblocks to postgis...")
command = 'ogr2ogr -overwrite -progress -f "PostgreSQL" ' \
        + 'PG:"host={host} port=5432 dbname={db} '.format(host = db_host,db = db) \
        + 'user={user} password = {pwd}" '.format(user = db_user,pwd = db_pwd) \
        + '{gdb} "{feature}" '.format(gdb = gdb_path,feature = 'meshblocks') \
        + '-lco geometry_name="geom"'
sp.call(command, shell=True)

# connect to the PostgreSQL server and ensure privileges are granted for all public tables
conn = psycopg2.connect(dbname=db, user=db_user, password=db_pwd)
curs = conn.cursor()
curs.execute(grant_query)
conn.commit()
conn.close()

# field_names = [f.name for f in arcpy.ListFields(featureclass)]
with arcpy.da.SearchCursor('layer', meshblock_id) as cursor:
    mb_id_list = sorted({row[0] for row in cursor})
   
# import dwelling data
df = pandas.read_csv(dwellings)

# dwelling meshblock id to string
df[dwellings_id] = df[dwellings_id].astype(str)

# restrict dwellings list to those mehsblocks within study region
df = df[df[dwellings_id].isin(mb_id_list)]  

# restrict dwellings to those meshblocks with dwellings > 0
df = df[df['Dwelling']>0]

# make column headers lower case for sql
df.columns = [x.lower() for x in df.columns]

# create dwellings table in postgresql 
engine = create_engine("postgresql://{user}:{pwd}@{host}/{db}".format(user = db_user,
                                                                 pwd  = db_pwd,
                                                                 host = db_host,
                                                                 db   = db))
df.to_sql(name='dwellings',con=engine,if_exists='replace')

# connect to the PostgreSQL server
conn = psycopg2.connect(dbname=db, user=db_user, password=db_pwd)
curs = conn.cursor()

# dwellings to postgis
create_table = '''DROP TABLE IF EXISTS mb_dwellings;
   CREATE TABLE mb_dwellings AS
     SELECT * FROM
     dwellings LEFT JOIN meshblocks
     ON dwellings.{1} = meshblocks.{0};
    '''.format(meshblock_id.lower(),dwellings_id.lower())

# drop table if it already exists
curs.execute(create_table)
conn.commit()
# explicitly grant permissions
curs.execute(grant_query)
conn.commit()
conn.close()

# Copy joined, cropped Urban Metro meshblock + dwellings feature from postgis to project geodatabase
arcpy.env.workspace = db_sde_path
arcpy.CopyFeatures_management('public.mb_dwellings', os.path.join(gdb_path,'mb_dwellings'))

# output to completion log					
script_running_log(script, task, start, locale)
