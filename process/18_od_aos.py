# Script:  12_od_aos_list_analysis.py
# Purpose: Calcault distance to nearest AOS within 3.2km, 
#          or if none within 3.2km then distance to closest
# Authors: Carl Higgs

import arcpy, arcinfo
import os
import time
import multiprocessing
import sys
import psycopg2 
from sqlalchemy import create_engine
import numpy as np
from progressor import progressor

from script_running_log import script_running_log

# Import custom variables for National Liveability indicator process
from _project_setup import *

# simple timer for log file
start = time.time()
script = os.path.basename(sys.argv[0])
task = 'OD matrix - distance from parcel to closest POS of any size'

# INPUT PARAMETERS

# ArcGIS environment settings
arcpy.env.workspace = gdb_path  
# create project specific folder in temp dir for scratch.gdb, if not exists
if not os.path.exists(os.path.join(temp,db)):
    os.makedirs(os.path.join(temp,db))
    
arcpy.env.scratchWorkspace = os.path.join(temp,db)  
arcpy.env.qualifiedFieldNames = False  
arcpy.env.overwriteOutput = True 

# Specify geodatabase with feature classes of "origins"
origin_points   = parcel_dwellings
origin_pointsID = points_id

## specify "destinations"
os_source = 'open_space_areas'
aos_points   =  'aos_nodes_30m_line'
aos_pointsID =  'aos_entryid'

hexStart = 0

# SQL Settings
sqlTableName  = "od_aos"
sqlChunkify = 600
        
# initiate postgresql connection
conn = psycopg2.connect(database=db, user=db_user, password=db_pwd)
curs = conn.cursor()

# get list of hexes over which to iterate
engine = create_engine("postgresql://{user}:{pwd}@{host}/{db}".format(user = db_user,
                                                                 pwd  = db_pwd,
                                                                 host = db_host,
                                                                 db   = db))
curs.execute("SELECT sum(parcel_count) FROM hex_parcels;")
total_parcels = int(list(curs)[0][0])
progress_table = 'od_aos_progress'

# get pid name
pid = multiprocessing.current_process().name
# create initial OD cost matrix layer on worker processors
if pid !='MainProcess':
  # Make OD cost matrix layer
  result_object = arcpy.MakeODCostMatrixLayer_na(in_network_dataset = in_network_dataset, 
                                                 out_network_analysis_layer = "ODmatrix", 
                                                 impedance_attribute = "Length", 
                                                 default_cutoff = aos_threshold,
                                                 UTurn_policy = "ALLOW_UTURNS", 
                                                 hierarchy = "NO_HIERARCHY", 
                                                 output_path_shape = "NO_LINES")                                 
  outNALayer = result_object.getOutput(0)
  
  #Get the names of all the sublayers within the service area layer.
  subLayerNames = arcpy.na.GetNAClassNames(outNALayer)
  #Store the layer names that we will use later
  originsLayerName = subLayerNames["Origins"]
  destinationsLayerName = subLayerNames["Destinations"]
  linesLayerName = subLayerNames["ODLines"]
  
  # you may have to do this later in the script - but try now....
  ODLinesSubLayer = arcpy.mapping.ListLayers(outNALayer, linesLayerName)[0]
  fields = ['Name', 'Total_Length']
  
  arcpy.MakeFeatureLayer_management(hex_grid, "hex_layer")     
  arcpy.MakeFeatureLayer_management(aos_points, "aos_pointsLayer")   
  arcpy.MakeFeatureLayer_management(origin_points,"origin_pointsLayer")   

  
# Establish preliminary SQL step to filter down Origin-Destination combinations 
# by minimum distance to an entry node
recInsert      = '''
  INSERT INTO {table} ({id}, aos_id, node, distance)  
  SELECT DISTINCT ON (gnaf_pid, aos_id) gnaf_pid, aos_id, node, distance
   FROM  
   (VALUES 
  '''.format(id = origin_pointsID.lower(),
             table = sqlTableName)          

# Aggregate the minimum distance OD combinations into a list
# node is retained for verification purposes; 
# ie. we can visually evaluate that the distance to dest checks out  
# Optionally, other attributes could be joined using a 'post' clause with a left join
# and aggregated at this point (see earlier code versions).
# However, it is probably more optimal to keep AOS attributes seperate.
# If making a query re: a specific AOS subset, the AOS IDs for the relevant 
# subset could first be identified; then the OD AOS results could be checked
# to return only those Addresses with subset AOS IDs recorded within the 
# required distance
recUpdate      = '''
  ) v({id}, aos_id, node, distance) 
  ORDER BY gnaf_pid, aos_id, distance ASC 
  ON CONFLICT ({id}, aos_id) 
    DO UPDATE
      SET node = EXCLUDED.node, 
          distance = EXCLUDED.distance 
       WHERE EXCLUDED.distance < od_aos.distance;
  '''.format(id = origin_pointsID.lower())  
 
parcel_count = int(arcpy.GetCount_management(origin_points).getOutput(0))  
denominator = parcel_count              
                   
 
## Functions defined for this script    
def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]
        
# Worker/Child PROCESS
def ODMatrixWorkerFunction(hex): 
  # print(hex)
  # Connect to SQL database 
  try:
    conn = psycopg2.connect(database=db, user=db_user, password=db_pwd)
    curs = conn.cursor()
  except:
    print("SQL connection error")
    print(sys.exc_info()[1])
    return 100
  # make sure Network Analyst licence is 'checked out'
  arcpy.CheckOutExtension('Network')
 
  # Worker Task is hex-specific by definition/parallel
  #     Skip if hex was finished in previous run
  hexStartTime = time.time()
  if hex[0] < hexStart:
    return(1)
    
  try:
    count = 0
    place = 'At the beginning...'
    to_do_points = hex[1]  
    A_pointCount = len(to_do_points)
    # process ids in groups of 500 or fewer
    place = 'before hex selection'
    hex_selection = arcpy.SelectLayerByAttribute_management("hex_layer", where_clause = 'OBJECTID = {}'.format(hex[0]))
    place = 'before skip empty B hexes'
    # print(place)   
    B_selection = arcpy.SelectLayerByLocation_management('aos_pointsLayer', 'WITHIN_A_DISTANCE', hex_selection, '3200 Meters')
    B_pointCount = int(arcpy.GetCount_management(B_selection).getOutput(0))
    if B_pointCount == 0:  
      # It appears that no parks are accessible, so we record a null value for ids so that if processing
      # recommences this hex will be skipped.  If for some reason an entry for this ID already exists, 
      # no action is taken.
      # To side step non-null constrain on AOS ID, we insert -9999 to indicate a no park within 3.2km
      evaluate_os_intersection = '''
      INSERT INTO od_aos ({id},aos_id)
      SELECT {id},-9999
      FROM parcel_dwellings p
      WHERE hex_id = {hex};
       '''.format(id = points_id.lower(),
                 hex = hex[0])
      curs.execute(evaluate_os_intersection)
      conn.commit()        
    if B_pointCount > 0:  
      place = "Buffer intersects AOS, so check if hex intersects also"
      # print(place)
      hex_intersects = '''
      SELECT 1 
       WHERE EXISTS (SELECT 1 
                       FROM  {region}_2018_hex_3000m_diag h, 
                             {os_source} p 
                      WHERE h.objectid = {hex} 
                        AND ST_Intersects(h.geom,p.geom) 
                   GROUP BY h.objectid);
      '''.format(region = region,hex = hex[0],os_source = os_source)
      curs.execute(hex_intersects)
      hex_intersects = list(curs)
      if len(hex_intersects) > 0:
        evaluate_os_intersection = '''
        INSERT INTO od_aos ({id}, aos_id,distance)
        SELECT {id}, 
                aos_id,
                0
        FROM parcel_dwellings p, open_space_areas o
        WHERE hex_id = {hex} 
        AND ST_Intersects(p.geom,o.geom)
        ON CONFLICT ({id}, aos_id) 
          DO UPDATE
             SET distance = 0;
          '''.format(id = points_id.lower(),
                    hex = hex[0])
        curs.execute(evaluate_os_intersection)
        conn.commit()  
      # Iterate over chunks of points 
      for chunk in chunks(to_do_points,sqlChunkify):
        A_selection = arcpy.SelectLayerByAttribute_management("origin_pointsLayer", 
                        where_clause = '''hex_id = {hex} AND {id} IN ('{id_list}')'''.format(hex = hex[0],
                                                                                         id = origin_pointsID,
                                                                                         id_list = "','".join(chunk)))
        # Process OD Matrix Setup
        place = "add unprocessed address points"
        # print(place)
        arcpy.AddLocations_na(in_network_analysis_layer = outNALayer, 
            sub_layer                      = originsLayerName, 
            in_table                       = A_selection, 
            field_mappings                 = "Name {} #".format(origin_pointsID), 
            search_tolerance               = "{} Meters".format(tolerance), 
            search_criteria                = "{} SHAPE;{} NONE".format(network_edges,network_junctions), 
            append                         = "CLEAR", 
            snap_to_position_along_network = "NO_SNAP", 
            exclude_restricted_elements    = "INCLUDE",
            search_query                   = "{} #;{} #".format(network_edges,network_junctions))
        place = "add in parks"
        # print(place
        arcpy.AddLocations_na(in_network_analysis_layer = outNALayer, 
          sub_layer                      = destinationsLayerName, 
          in_table                       = B_selection, 
          field_mappings                 = "Name {} #".format(aos_pointsID), 
          search_tolerance               = "{} Meters".format(tolerance), 
          search_criteria                = "{} SHAPE;{} NONE".format(network_edges,network_junctions), 
          append                         = "CLEAR", 
          snap_to_position_along_network = "NO_SNAP", 
          exclude_restricted_elements    = "INCLUDE",
          search_query                   = "{} #;{} #".format(network_edges,network_junctions))    
        place = 'Solve'
        # print(place)
        result = arcpy.Solve_na(outNALayer, terminate_on_solve_error = "CONTINUE")
        if result[1] == u'true':
          place = 'After solve'
          # Extract lines layer, export to SQL database
          outputLines = arcpy.da.SearchCursor(ODLinesSubLayer, fields)        
          chunkedLines = list()
          place = 'before outputLine loop'
          for outputLine in outputLines:
            count += 1
            od_pair = outputLine[0].split('-')
            pid = od_pair[0].encode('utf-8').strip(' ')
            aos_pair = od_pair[1].split(',')
            aos = int(aos_pair[0])
            node = int(aos_pair[1])
            distance = int(round(outputLine[1]))
            place = "before chunk append, gnaf = {}".format(pid)
            chunkedLines.append('''('{pid}',{aos},{node},{distance})'''.format(pid = pid,
                                                                               aos = aos,
                                                                               node = node,
                                                                               distance  = distance))
          place = "before execute sql, gnaf = {}".format(pid)
          curs.execute('''{insert}{data}{update}'''.format(insert = recInsert,
                                                           data   = ','.join(chunkedLines),
                                                           update = recUpdate))
          place = "before commit, gnaf = {}".format(pid)
          conn.commit()
        if arcpy.Exists(result):  
          arcpy.Delete_management(result)   
    # aggregate processed results as jsonb string
    # may be more efficient memory wise to do this as we go with parallel workers
    json_insert = '''
      INSERT INTO {table}_jsonb ({id},attributes)  
      SELECT o.{id}, 
              jsonb_agg(jsonb_strip_nulls(to_jsonb( 
                  (SELECT d FROM 
                      (SELECT 
                         aos_id,
                         distance
                         ) d)))) AS attributes 
      FROM  od_aos o
      WHERE EXISTS 
      (SELECT 1 
         FROM parcel_dwellings t
        WHERE t.hex_id = {hex} 
          AND t.{id} = o.{id})
      GROUP BY o.{id}
      ON CONFLICT ({id}) DO NOTHING'''.format(id = points_id.lower(), hex = hex[0], table = sqlTableName)    
    curs.execute(json_insert)
    conn.commit()
    # update current progress
    curs.execute('''UPDATE {progress_table} SET processed = processed+{count}'''.format(progress_table = progress_table,
                                                                                                 count = A_pointCount))
    conn.commit()
    curs.execute('''SELECT processed from {progress_table}'''.format(progress_table = progress_table))
    progress = int(list(curs)[0][0])
    progressor(progress,total_parcels,start,'''{}/{}; last hex processed: {}, at {}'''.format(progress,total_parcels,hex[0],time.strftime("%Y%m%d-%H%M%S"))) 
  except:
    print('''Error: {}
             Place: {}
      '''.format( sys.exc_info(),place))   

  finally:
    arcpy.CheckInExtension('Network')
    conn.close()

  
# MAIN PROCESS
if __name__ == '__main__':
  # simple timer for log file
  start = time.time()
  script = os.path.basename(sys.argv[0])
  task = 'Create OD cost matrix for parcel points to closest POS (any size)'  # Do stuff  
  # Task name is now defined
  print("Commencing task ({}):\n{} at {}".format(db,task,time.strftime("%Y%m%d-%H%M%S")))
  
  # connect to sql
  conn = psycopg2.connect(database=db, user=db_user, password=db_pwd)
  curs = conn.cursor()
  
  print('''Ensure previous results have been marked as 'incorrect'.
  That is, check that a tables 'od_aos_incorrect','od_aos_jsonb_incorrect' and 'od_aos_progress_incorrect' all exist; if not these tables will be marked as incorrect; if so, then we proceed assuming that any od_aos tables already existing are the new amended versions''')
  curs.execute('''SELECT 1 WHERE to_regclass('public.od_aos_incorrect') IS NOT NULL AND to_regclass('public.od_aos_jsonb_incorrect') IS NOT NULL AND to_regclass('public.od_aos_progress_incorrect') IS NOT NULL;''')
  res = curs.fetchone()
  if res is None:
    for table in ['od_aos', 'od_aos_jsonb', 'od_aos_progress']:
      mark_incorrect_sql = '''ALTER TABLE IF EXISTS {table} RENAME TO {table}_incorrect;'''.format(table = table)
      print("Executing: {}... ".format(mark_incorrect_sql)),
      curs.execute(mark_incorrect_sql)
      conn.commit()
      print("Done.")
    curs.execute('''SELECT 1 WHERE to_regclass('public.od_aos_incorrect') IS NOT NULL AND to_regclass('public.od_aos_jsonb_incorrect') IS NOT NULL AND to_regclass('public.od_aos_progress_incorrect') IS NOT NULL;''')
    res = curs.fetchone()
    if res is None:
      print("At least one of these tables still does not exist, which implies at least one wasn't calculated in the first instance; or they have been manually renamed to something else, or deleted. So, we create an empty 'incorrect' table just to mark that we have checked no incorrect results persist unmarked as being incorrect")
      for table in ['od_aos', 'od_aos_jsonb', 'od_aos_progress']:
        create_marked_table = '''CREATE TABLE IF NOT EXISTS {table}_incorrect AS SELECT NULL;'''.format(table = table)
        print("Executing: {}... ".format(create_marked_table)),
        curs.execute(create_marked_table)
        conn.commit()
        print("Done.")
    
  print("Create Area of Open Space (AOS) within 3200m list table"),
  createTable     = '''
  -- DROP TABLE IF EXISTS {table};
  CREATE TABLE IF NOT EXISTS {table}
  (
  {id} varchar, 
  aos_id int,  
  node int,  
  distance int,
  PRIMARY KEY ({id}, aos_id) 
  );
  '''.format(table = sqlTableName, id = origin_pointsID.lower())
  curs.execute(createTable)
  conn.commit()
  print("Done.")    
  print("Create Area of Open Space (AOS) JSONB aggregate table"),
  createTable     = '''
  -- DROP TABLE IF EXISTS od_aos_jsonb;
  CREATE TABLE IF NOT EXISTS od_aos_jsonb
  (
  {id} varchar PRIMARY KEY, 
  attributes jsonb 
  );
  '''.format(id = origin_pointsID.lower())
  curs.execute(createTable)
  conn.commit()
  print("Done.")
  ## LATER index on gnaf_id, query

  print("Create a table for tracking progress... "), 
  od_aos_progress_table = '''
    DROP TABLE IF EXISTS od_aos_progress;
    CREATE TABLE IF NOT EXISTS od_aos_progress 
       (processed int);
    '''
  curs.execute(od_aos_progress_table)
  conn.commit()
  print("Done.")
  
  
  print("Divide work by hexes for multiprocessing, only for parcels not already processed... "),
  # evaluated against od_aos_jsonb as the id field has no duplicates in this table
  antijoin = '''
    SELECT p.hex_id, 
           jsonb_agg(jsonb_strip_nulls(to_jsonb(p.{id}))) AS incomplete
    FROM parcel_dwellings p
    WHERE NOT EXISTS 
    (SELECT 1 FROM od_aos_jsonb s WHERE s.{id} = p.{id})
    GROUP BY p.hex_id;
  '''.format(id = points_id.lower())
  incompletions = pandas.read_sql_query(antijoin,
                                    con=engine)
  to_do_list = incompletions.apply(tuple, axis=1).tolist()
  to_do_list = [[int(x[0]),[p.encode('utf8') for p in x[1]]] for x in to_do_list]
  print("Done.")

  print("Calculate the sum total of parcels that need to be processed, and determine the number already processed"),
  to_process = incompletions["incomplete"].str.len().sum()
  processed = total_parcels - to_process
  curs.execute('''INSERT INTO od_aos_progress (processed) VALUES ({})'''.format(processed))
  conn.commit()
  print("Done.")

  print("Commence multiprocessing...")  
  pool = multiprocessing.Pool(nWorkers)
  pool.map(ODMatrixWorkerFunction, to_do_list, chunksize=1)
  
  print("Create indices on attributes")
  curs.execute('''CREATE INDEX IF NOT EXISTS idx_od_aos_jsonb ON od_aos_jsonb ({id});'''.format(id = points_id.lower()))
  curs.execute('''CREATE INDEX IF NOT EXISTS idx_od_aos_jsonb_aos_id ON od_aos_jsonb ((attributes->'aos_id'));''')
  curs.execute('''CREATE INDEX IF NOT EXISTS idx_od_aos_jsonb_distance ON od_aos_jsonb ((attributes->'distance'));''')
  conn.commit()
  
  # output to completion log    
  script_running_log(script, task, start, locale)
  conn.close()