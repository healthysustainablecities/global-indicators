# Script:  createODmatrix_Loop_parallelised_closestAB.py
# Purpose: This script finds for each A point the closest B point along a network.
#              - it uses parallel processing
#              - it outputs to an sql database 
# Authors: Carl Higgs, Koen Simons
#
# Note: Following processing, I would recommend you check out the log_od_distances table 
# in postgresql and consider the entries with 'no solution' - are these reasonable?
# For example - in psql run query 
# SELECT * FROM log_od_distances WHERE status = 'no solution' ORDER BY random() limit 20;
# Now, using ArcMap check out those hexes and destinations - can you explain why there 
# was no solution?  In my trial I was using a demo road network feature, and such results
# returned where parcels could not be snapped to a road network.  So, these results should 
# be considered critically, if they occur.  Is it a failing in our process, and if so can
# we fix it?

import arcpy, arcinfo
import os
import time
import multiprocessing
import sys
import psycopg2 
import numpy as np
from progressor import progressor

from script_running_log import script_running_log

# Import custom variables for National Liveability indicator process
from _project_setup import *

# simple timer for log file
start = time.time()
script = os.path.basename(sys.argv[0])

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

## specify "destination_points" (e.g. destinations)
destination_pointsID = destination_id

# Get a list of feature 
featureClasses = arcpy.ListFeatureClasses()

# Processing is undertake for any value > hexStart
# So, if you want to start from a specific hex number,
# you could change this to a larger value
hexStart = 0

# SQL Settings
## Note - this used to be 'dist_cl_od_parcel_dest' --- simplified to 'od_closest'
od_distances  = "od_closest"
log_table    = "log_od_distances"
queryPartA = "INSERT INTO {} VALUES ".format(od_distances)

sqlChunkify = 500
  
# initiate postgresql connection
conn = psycopg2.connect(database=db, user=db_user, password=db_pwd)
curs = conn.cursor()  

# define reduced set of destinations and cutoffs (ie. only those with cutoffs defined)
curs.execute("SELECT dest_name,dest_class,cutoff_closest FROM dest_type WHERE cutoff_closest IS NOT NULL AND count > 0;")
destination_list = list(curs)

# tally expected hex-destination result set  
curs.execute("SELECT COUNT(*) FROM parcel_dwellings;")
completion_goal = list(curs)[0][0] * len(set([x[1] for x in destination_list]))

# get pid name
pid = multiprocessing.current_process().name

# Define query to create table
createTable     = '''
  --DROP TABLE IF EXISTS {0};
  CREATE TABLE IF NOT EXISTS {0}
  ({1} varchar NOT NULL ,
   dest_class varchar NOT NULL ,
   dest_name varchar NOT NULL ,
   oid bigint NOT NULL ,
   distance integer NOT NULL, 
   threshold  int,
   ind_hard   int,
   ind_soft   double precision,
   PRIMARY KEY({1},dest_class)
   );
   '''.format(od_distances, origin_pointsID)

queryPartA      = '''
  INSERT INTO {} VALUES
  '''.format(od_distances)

createTable_log     = '''
  --DROP TABLE IF EXISTS {0};
  CREATE TABLE IF NOT EXISTS {0}
    (hex integer NOT NULL, 
    parcel_count integer NOT NULL, 
    dest_name varchar, 
    status varchar, 
    mins double precision,
    PRIMARY KEY(hex,dest_name)
    );
    '''.format(log_table)    

queryInsert      = '''
  INSERT INTO {} VALUES
  '''.format(log_table)          

queryUpdate      = '''
  ON CONFLICT ({0},{4}) 
  DO UPDATE SET {1}=EXCLUDED.{1},{2}=EXCLUDED.{2},{3}=EXCLUDED.{3}
  '''.format('hex','parcel_count','status','mins','dest_name')            
    
# Define log file write method
def writeLog(hex = 0, AhexN = 'NULL', Bcode = 'NULL', status = 'NULL', mins= 0, create = log_table):
  try:
    if create == 'create':
      curs.execute(createTable_log)
      conn.commit()
      
    else:
      moment = time.strftime("%Y%m%d-%H%M%S")
      # print to screen regardless
      # print('Hex:{:5d} A:{:8s} Dest:{:8s} {:15s} {:15s}'.format(hex, str(AhexN), str(Bcode), status, moment))     
      # write to sql table
      curs.execute("{0} ({1},{2},'{3}','{4}',{5}) {6}".format(queryInsert,hex, AhexN, Bcode,status, mins, queryUpdate))
      conn.commit()  
  except:
    print("ERROR: {}".format(sys.exc_info()))
    raise

# Worker/Child PROCESS
def ODMatrixWorkerFunction(hex): 
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
  # Skip if hex was finished in previous run
  hexStartTime = time.time()
  if hex < hexStart:
    return(1)
    
  try:    
    # identify any points from this hex without a sausage buffer; lets not consider them
    exclude_points = ""
    # sql = '''SELECT gnaf_pid FROM no_sausage WHERE hex_id = {}'''.format(hex)
    # curs.execute(sql)
    # if len(list(curs)) > 0:
      # exclude_points = '''AND {id} NOT IN ('{exclude}')'''.format(id = origin_pointsID,
                                                                  # exclude = ','.join([x[0] for x in list(curs)]))
    # select origin points 
    arcpy.MakeFeatureLayer_management (origin_points, "origin_points_layer")
    origin_selection = arcpy.SelectLayerByAttribute_management("origin_points_layer", 
                          where_clause = 'hex_id = {hex_id} {exclude_points}'.format(hex_id = hex,
                                                                                     exclude_points= exclude_points))
    origin_point_count = int(arcpy.GetCount_management(origin_selection).getOutput(0))
    # Skip hexes with zero adresses
    if origin_point_count == 0:
        writeLog(hex,0,'NULL',"no valid origin points",(time.time()-hexStartTime)/60)
        return(2)
    
    # make destination feature layer
    arcpy.MakeFeatureLayer_management (study_destinations, "destination_points_layer")        
    
    # fetch list of successfully processed destinations for this hex, if any
    curs.execute("SELECT dest_name FROM {} WHERE hex = {}".format(log_table,hex))
    completed_dest = [x[0] for x in list(curs)]
    remaining_dest_list = [x for x in destination_list if x[0] not in completed_dest]
    
    # Make OD cost matrix layer
    result_object = arcpy.MakeODCostMatrixLayer_na(in_network_dataset = in_network_dataset, 
                                                   out_network_analysis_layer = "ODmatrix", 
                                                   impedance_attribute = "Length", 
                                                   default_number_destinations_to_find = 1,
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
    
    for destination_points in remaining_dest_list:
      dest_name = destination_points[0]
      dest_class = destination_points[1]
      dest_cutoff_threshold = destination_points[2]
      destStartTime = time.time()
      # select destination points 
      destination_selection = arcpy.SelectLayerByAttribute_management("destination_points_layer", where_clause = "dest_name = '{}'".format(dest_name))
      # OD Matrix Setup
      arcpy.AddLocations_na(in_network_analysis_layer = outNALayer, 
          sub_layer                      = originsLayerName, 
          in_table                       = origin_selection, 
          field_mappings                 = "Name {} #".format(origin_pointsID), 
          search_tolerance               = "{} Meters".format(tolerance), 
          search_criteria                = "{} SHAPE;{} NONE".format(network_edges,network_junctions), 
          append                         = "CLEAR", 
          snap_to_position_along_network = "NO_SNAP", 
          exclude_restricted_elements    = "INCLUDE",
          search_query                   = "{} #;{} #".format(network_edges,network_junctions))
      arcpy.AddLocations_na(in_network_analysis_layer = outNALayer, 
          sub_layer                      = destinationsLayerName, 
          in_table                       = destination_selection, 
          field_mappings                 = "Name {} #".format(destination_pointsID), 
          search_tolerance               = "{} Meters".format(tolerance), 
          search_criteria                = "{} SHAPE;{} NONE".format(network_edges,network_junctions), 
          append                         = "CLEAR", 
          snap_to_position_along_network = "NO_SNAP", 
          exclude_restricted_elements    = "INCLUDE",
          search_query                   = "{} #;{} #".format(network_edges,network_junctions))
      # Process: Solve
      result = arcpy.Solve_na(outNALayer, terminate_on_solve_error = "CONTINUE")
      if result[1] == u'false':
        writeLog(hex,origin_point_count,dest_name,"no solution",(time.time()-destStartTime)/60)
      else:
        # Extract lines layer, export to SQL database
        outputLines = arcpy.da.SearchCursor(ODLinesSubLayer, fields)
        count = 0
        chunkedLines = list()
        for outputLine in outputLines :
          count += 1
          origin_id      = outputLine[0].split('-')[0].strip(' ')
          dest_id   = outputLine[0].split('-')[1].split(',')
          dest_class = dest_id[0].strip(' ')
          dest_id   = dest_id[1].strip(' ')
          distance  = int(round(outputLine[1]))
          threshold = float(dest_cutoff_threshold)
          ind_hard  = int(distance < threshold)
          ind_soft = 1 - 1.0 / (1+np.exp(-soft_threshold_slope*(distance-threshold)/threshold))
          chunkedLines.append('''('{point_id}','{d_class}','{d_name}',{d_id},{distance},{threshold},{ind_h},{ind_s})'''.format(point_id  = origin_id,
                                                                                                                               d_class = dest_class,
                                                                                                                               d_name = dest_name,
                                                                                                                               d_id   = dest_id,
                                                                                                                               distance  = distance,
                                                                                                                               threshold = threshold,
                                                                                                                               ind_h  = ind_hard,
                                                                                                                               ind_s  = ind_soft))
          if(count % sqlChunkify == 0):
            sql = '''
            INSERT INTO {od_distances} AS o VALUES {values} 
            ON CONFLICT ({id},dest_class) 
            DO UPDATE 
            SET dest_name = EXCLUDED.dest_name,
                oid       = EXCLUDED.oid,
                distance  = EXCLUDED.distance,
                ind_hard  = EXCLUDED.ind_hard,
                ind_soft  = EXCLUDED.ind_soft
            WHERE EXCLUDED.distance < o.distance;
            '''.format(od_distances=od_distances, 
                        values = ','.join(chunkedLines),
                        id = origin_pointsID)
            curs.execute(sql)
            conn.commit()
            chunkedLines = list()
        if(count % sqlChunkify != 0):
          sql = '''
          INSERT INTO {od_distances} AS o VALUES {values} 
          ON CONFLICT ({id},dest_class) 
          DO UPDATE 
          SET dest_name = EXCLUDED.dest_name,
              oid       = EXCLUDED.oid,
              distance  = EXCLUDED.distance,
              ind_hard  = EXCLUDED.ind_hard,
              ind_soft  = EXCLUDED.ind_soft
          WHERE EXCLUDED.distance < o.distance;
          '''.format(od_distances=od_distances, 
                      values = ','.join(chunkedLines),
                      id = origin_pointsID)
          curs.execute(sql)
          conn.commit()
        writeLog(hex,origin_point_count,dest_name,"Solved",(time.time()-destStartTime)/60)
    # return worker function as completed once all destinations processed
    return 0
  except:
    print(sys.exc_info())

  finally:
    arcpy.CheckInExtension('Network')
    # Report on progress
    curs.execute("SELECT count(*) FROM od_closest WHERE dest_name IN (SELECT dest_name FROM dest_type);".format(log_table))
    progress = int(list(curs)[0][0]) 
    progressor(progress,completion_goal,start,"{numerator} / {denominator} parcel-destination combinations processed.".format(numerator = progress,denominator = completion_goal))
    # Close SQL connection
    conn.close()


    
# MAIN PROCESS
if __name__ == '__main__':
  # Task name is now defined
  task = 'Find closest of each destination type to origin'  # Do stuff
  print("Commencing task ({}): {} at {}".format(db,task,time.strftime("%Y%m%d-%H%M%S")))
  # print('''
  # Please note that this script assumes sausage buffers have previously been calculated, 
  # drawing upon the 'no_sausage' table to exclude any points listed there from consideration.
  # ''')
  try:
    conn = psycopg2.connect(database=db, user=db_user, password=db_pwd)
    curs = conn.cursor()

    # create OD matrix table
    curs.execute(createTable)
    conn.commit()

  except:
    print("SQL connection error")
    print(sys.exc_info()[0])
    raise
   
  print("Initialise log file..."),
  writeLog(create='create')
  print(" Done.")
  
  print("Setup a pool of workers/child processes and split log output..."),
  # Parallel processing setting
  # (now set as parameter in _project_configuration xlsx file)
  pool = multiprocessing.Pool(processes=nWorkers)
  print(" Done.")

  print("Iterate over hexes...")
  # get list of hexes over which to iterate
  curs.execute("SELECT hex FROM hex_parcels;")
  hex_list = list(curs)   
  iteration_list = np.asarray([x[0] for x in hex_list])
  # # Iterate process over hexes across nWorkers
  pool.map(ODMatrixWorkerFunction, iteration_list, chunksize=1)
  
  # output to completion log    
  conn.close()
  script_running_log(script, task, start, locale)
