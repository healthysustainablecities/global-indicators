# Script:  createSausageBuffer_Loop.py
# Purpose: This script creates sausage buffers for specified input distance.  
# It:
#  -- iterates over hexes not previously processed
#  -- it loops over points within hexes not previously processed
#  -- outputs the lines from a network service area of specified route length
#  -- the final line feature which is stored in the project postgresql database
#     is then buffered a specified distance
#        -- may be worth considering whether post-processing the st_buffer is worth it
#        -- best approach may be to not permanently st_buffer
#            - could just create a size attribute based on st_buffer
#                 - this is all we require as denominator to density measures
#                 - select by location/distance from existing line is used for catchment
# Input: requires network dataset, parcel points etc -- specified in config.ini
# 
# Note that you can modify the 'nWorkers' variable (line 48 at time of writing)
# to change the number of processors used.  On our computers, 7 should be safe.
# Or, you could use 4 and run two instances of the process (so if one finishes, 
# the other continues to process --- handy over the weekend.
#
# Carl Higgs and Koen Simons, 2016-2018

import arcpy, arcinfo
import glob
import time
import multiprocessing
import psycopg2 
import numpy as np
from shutil import copytree,rmtree,ignore_patterns
from progressor import progressor

from script_running_log import script_running_log

# Import custom variables for National Liveability indicator process
from _project_setup import *


# simple timer for log file
start = time.time()
script = os.path.basename(sys.argv[0])

# ArcGIS environment settings
arcpy.env.workspace = gdb_path  

# Specify points
points   = parcel_dwellings
denominator = int(arcpy.GetCount_management(points).getOutput(0))

# Output databases
sausage_buffer_table = "sausagebuffer_{}".format(distance)
nh_sausagebuffer_summary = "nh{}m".format(distance)

# if issues have arisen in processing, commencement hex and object may be specified here
hexStart    = 0
# set object floor - ie. objects subsequent to this within hex are processed
objectFloor = 0

# point chunk size (for looping within polygon)
group_by = 1000

## Log file details (including header row)
log_table = 'log_hex_sausage_buffer'

# temp --- using SSD copies to save write/read time, and avoid multiprocessing conflicts
if not os.path.exists(temp):
    os.makedirs(temp)

createTable_log     = '''
  --DROP TABLE IF EXISTS {0};
  CREATE TABLE IF NOT EXISTS {0}
    (hex integer PRIMARY KEY, 
    parcel_count integer NOT NULL, 
    status varchar, 
    moment varchar, 
    mins double precision
    );
    '''.format(log_table)        
          
queryInsert      = '''
  INSERT INTO {} VALUES
  '''.format(log_table)

queryUpdate      = '''
  ON CONFLICT ({0}) 
  DO UPDATE SET {1}=EXCLUDED.{1},{2}=EXCLUDED.{2},{3}=EXCLUDED.{3},{4}=EXCLUDED.{4} 
  '''.format('hex','parcel_count','status','moment','mins')  

createTable_sausageBuffer = '''
  --DROP TABLE IF EXISTS {0};
  CREATE TABLE IF NOT EXISTS {0}
    ({1} varchar PRIMARY KEY, 
     hex integer,
     geom geometry);  
  '''.format(sausage_buffer_table,points_id.lower())

createTable_processor_log = '''
  DROP TABLE IF EXISTS processor_log;
  CREATE TABLE IF NOT EXISTS processor_log
    (pid SERIAL PRIMARY KEY,
     name varchar);  
  '''
  
queryInsertSausage = '''
  INSERT INTO {} VALUES
  '''.format(sausage_buffer_table)  
  
# Define log file write method
def writeLog(hex = 0,parcel_count = 0,status = 'NULL',mins = 0, create = log_table):
  try:

    if create == 'create':  
      curs.execute(createTable_log)
      conn.commit()
      
      # print('{:>10} {:>15} {:>20} {:>15} {:>11}'.format('HexID','parcel_count','Status','Time','Minutes'))
    else:
      moment = time.strftime("%Y%m%d-%H%M%S")
      # print to screen regardless
      # print('{:9.0f} {:14.0f}  {:>19s} {:>14s}   {:9.2f}'.format(hex, parcel_count, status, moment, mins))
      
      # write to sql table
      curs.execute("{0} ({1},{2},'{3}','{4}',{5}) {6};".format(queryInsert,hex, parcel_count, status, moment, mins, queryUpdate))
      conn.commit()
      
  except:
    print('''Issue with log file using parameters:
             hex: {}  parcel_count: {}  status: {}   mins:  {}  create:  {}
             '''. format(hex, parcel_count, status, mins, create))

def unique_values(table, field):
  data = arcpy.da.TableToNumPyArray(table, [field])
  return np.unique(data[field])
  
# WORKER PROCESSORS pre-setup
if __name__ != '__main__': 
  # initiate postgresql connection
  conn = psycopg2.connect(database=db, user=db_user, password=db_pwd)
  curs = conn.cursor()  
  
  # fetch list of assigned processors in range 1 to n, if any
  # Create temporary PID specific scratch geodatabase if not already existing
  curs.execute("SELECT pid FROM processor_log WHERE name = '{}';".format(multiprocessing.current_process().name))
  pid = [f[0] for f in list(curs)]
  if len(pid) > 0:
    pid = pid[0]
  if len(pid)==0:    
    curs.execute("INSERT INTO processor_log (name) VALUES ('{}');".format(multiprocessing.current_process().name))
    conn.commit()
    curs.execute("SELECT pid FROM processor_log WHERE name = '{}';".format(multiprocessing.current_process().name))
    pid = [f[0] for f in list(curs)][0] 
  
  # any new processes commencing must be reassigned to work from one of n scratch gdb
  if int(pid) > nWorkers:
    curs.execute("DELETE FROM processor_log WHERE pid = {};")
    conn.commit()
    curs.execute("SELECT pid FROM processor_log;".format(int(pid)))
    processor_list = [f[0] for f in list(curs)]
    processor_number = next(iter(set(range(min(processor_list)+1, max(processor_list))) - set(processor_list)))
    pid = processor_number
    curs.execute("INSERT INTO processor_log VALUES ({pid}, '{}');".format(pid, multiprocessing.current_process().name))
    conn.commit()
    
  temp_gdb = os.path.join(temp,"scratch_{}_{}".format(db,pid))
  # create project specific folder in temp dir for scratch.gdb, if not exists
  if not os.path.exists(temp_gdb):
      os.makedirs(temp_gdb)
      
  arcpy.env.scratchWorkspace = temp_gdb 
  arcpy.env.qualifiedFieldNames = False  
  arcpy.env.overwriteOutput = True 

  # preparatory set up
  # Process: Make Service Area Layer
  outSAResultObject = arcpy.MakeServiceAreaLayer_na(in_network_dataset = in_network_dataset, 
                                out_network_analysis_layer = os.path.join(arcpy.env.scratchGDB,"ServiceArea"), 
                                impedance_attribute = "Length",  
                                travel_from_to = "TRAVEL_FROM", 
                                default_break_values = "{}".format(distance), 
                                line_type="TRUE_LINES",
                                overlap="OVERLAP", 
                                polygon_type="NO_POLYS", 
                                lines_source_fields="NO_LINES_SOURCE_FIELDS", 
                                hierarchy="NO_HIERARCHY")
                                
  outNALayer = outSAResultObject.getOutput(0)
  
  #Get the names of all the sublayers within the service area layer.
  subLayerNames = arcpy.na.GetNAClassNames(outNALayer)
  #Store the layer names that we will use later
  facilitiesLayerName = subLayerNames["Facilities"]
  linesLayerName = subLayerNames["SALines"]
  linesSubLayer = arcpy.mapping.ListLayers(outNALayer,linesLayerName)[0]
  facilitiesSubLayer = arcpy.mapping.ListLayers(outNALayer,facilitiesLayerName)[0] 

  
  
# Worker/Child PROCESS main function
def CreateSausageBufferFunction(hex): 
  # initiate postgresql connection
  conn = psycopg2.connect(database=db, user=db_user, password=db_pwd)
  curs = conn.cursor() 
  
  # Worker Task is hex-specific by definition/parallel
  hexStartTime = time.time()
  
  # fcBufferLines  = "Lines_Buffer_{}".format(hex)
  fcLines  = os.path.join(arcpy.env.scratchGDB,"Lines")
  
  if hex < hexStart:
    # print('hex {} is prior to requested start point, hex {} and is assumed processed; Skipping.'.format(hex,str(hexStart)))
    return(1)
    
  # make sure Network Analyst licence is 'checked out'
  arcpy.CheckOutExtension('Network')
  
  # list of OIDs to iterate over
  antijoin = '''
    SELECT p.{id}
    FROM parcel_dwellings p
    WHERE hex_id = {hex}
    AND NOT EXISTS 
    (SELECT 1 FROM {table} s WHERE s.{id} = p.{id});
  '''.format(id = points_id.lower(), hex  = hex, table = sausage_buffer_table)
  curs.execute(antijoin)
  point_id_list = [x[0] for x in  list(curs)]
  valid_pointCount = len(point_id_list) 
  # Prepare to loop over points within polygons
  where_clause = '''"HEX_ID" = {hex} AND "{id}" in ('{id_list}')'''.format(hex = hex, 
                                                                   id  = points_id,
                                                                   id_list = "','".join(point_id_list))
  arcpy.MakeFeatureLayer_management(points, 
                                    "selection_{}".format(pid), 
                                    where_clause = where_clause)
  pointCount = int(arcpy.GetCount_management("selection_{}".format(pid)).getOutput(0))
  
  if pointCount == 0:
    # print('No unprocessed parcels within hex {}; Skipping.'.format(hex))
    return(2)
    
  if hex==hexStart:
    count =  max(1,(objectFloor//group_by)+1)
    current_floor =  objectFloor
    
  else:
    count = 1          
    current_floor = 0    

  if valid_pointCount == 0:
    return(3)  
  
  # commence iteration
  row_count = 0
  while (current_floor < valid_pointCount):  
    try:
      # set chunk bounds
      # eg. with group_by size of 200 and initial floor of OID = 0, 
      # initial current_max of 200, next current_floor is 201 with max of 400
      current_max = min(current_floor + group_by,valid_pointCount)
      if current_floor > 0:
        current_floor +=1
      
      chunkSQL = ''' "{id}" in ('{id_list}')'''.format(id = points_id,
                                                       id_list = "','".join(point_id_list[current_floor:current_max+1]))
      place = "after defining chunkSQL"

      chunk_group = arcpy.SelectLayerByAttribute_management("selection_{}".format(pid), where_clause = chunkSQL)
      place = "after defining chunk_group"
      
      # iterCount = int(arcpy.GetCount_management(chunk_group).getOutput(0))
      # print("now processing points {} to {} inclusive of {} unprocessed points within hex {} on processor {}".format(current_floor, current_max, valid_pointCount, hex, pid))
      
      # Process: Add Locations
      arcpy.AddLocations_na(in_network_analysis_layer = os.path.join(arcpy.env.scratchGDB,"ServiceArea"), 
                  sub_layer                      = facilitiesLayerName, 
                  in_table                       = chunk_group, 
                  field_mappings                 = "Name {} #".format(points_id), 
                  search_tolerance               = "{} Meters".format(tolerance), 
                  search_criteria                = "{} SHAPE;{} NONE".format(network_edges,network_junctions), 
                  append                         = "CLEAR", 
                  snap_to_position_along_network = "NO_SNAP", 
                  exclude_restricted_elements    = "INCLUDE",
                  search_query                   = "{} #;{} #".format(network_edges,network_junctions))
      place = "after AddLocations"      
      
      # Process: Solve
      arcpy.Solve_na(in_network_analysis_layer = os.path.join(arcpy.env.scratchGDB,"ServiceArea"), ignore_invalids = "SKIP",terminate_on_solve_error = "CONTINUE")
      place = "after Solve_na"      
      
      # Dissolve linesLayerName
      arcpy.Dissolve_management(in_features=linesSubLayer, 
                                out_feature_class=fcLines, 
                                dissolve_field="FacilityID", 
                                statistics_fields="", 
                                multi_part="MULTI_PART", 
                                unsplit_lines="DISSOLVE_LINES")
      place = "after Dissolve" 
      
      # Process: Join Field
      arcpy.MakeFeatureLayer_management(fcLines, "tempLayer_{}".format(pid))  
      place = "after MakeFeatureLayer of TempLayer" 
      
      arcpy.AddJoin_management(in_layer_or_view = "tempLayer_{}".format(pid), 
                               in_field    = "FacilityID", 
                               join_table  = facilitiesSubLayer,
                               join_field  = "ObjectId")
      place = "after AddJoin" 
      
      # write output line features within chunk to Postgresql spatial feature
      # Need to parse WKT output slightly (Postgresql doesn't take this M-values nonsense)
      with arcpy.da.SearchCursor("tempLayer_{}".format(pid),['Facilities.Name','Shape@WKT']) as cursor:
        for row in cursor:
          id =  row[0].encode('utf-8')
          wkt = row[1].encode('utf-8').replace(' NAN','').replace(' M ','')
          curs.execute(queryInsertSausage + "( '{0}',{1},ST_Buffer(ST_SnapToGrid(ST_GeometryFromText('{2}', {3}),{5}),{4}));".format(id,hex,wkt,srid,line_buffer,snap_to_grid))
          place = "after curs.execute insert sausage buffer" 
          conn.commit()
          place = "after conn.commit for insert sausage buffer" 
          row_count+=1  
      place = "after SearchCursor"           

      current_floor = (group_by * count)
      count += 1   
      place = "after increment floor and count"  
    except:
       print('''HEY, IT'S AN ERROR: {}
                ERROR CONTEXT: hex: {} current_floor: {} current_max: {} row_count: {}
                PLACE: {}'''.format(sys.exc_info(),hex,current_floor,current_max,row_count,place))
       writeLog(hex,row_count, "ERROR",(time.time()-hexStartTime)/60, log_table)   
       return(666)
    finally:
       # clean up  
       arcpy.Delete_management("tempLayer_{}".format(pid))
       arcpy.Delete_management(fcLines)

  curs.execute("SELECT COUNT({}) FROM {};".format(points_id.lower(),sausage_buffer_table))
  numerator = list(curs)
  numerator = int(numerator[0][0])
  writeLog(hex,row_count, "COMPLETED",(time.time()-hexStartTime)/60, log_table)   
  progressor(numerator,denominator,start,"{} / {} points processed. Last completed hex: {}".format(numerator,denominator,hex))
  arcpy.Delete_management("selection_{}".format(pid))
  arcpy.CheckInExtension('Network')
  conn.close()
  return(0)   
  
# MAIN PROCESS
if __name__ == '__main__': 
  # Task name is now defined
  task = 'creates {}{} sausage buffers for locations in {} based on road network {}'.format(distance,units,points,in_network_dataset)
  print("Commencing task: {} at {}".format(task,time.strftime("%Y%m%d-%H%M%S")))

  # initiate postgresql connection
  conn = psycopg2.connect(database=db, user=db_user, password=db_pwd)
  curs = conn.cursor() 
  
  # initiate log file
  writeLog(create='create')
  
  # create convenience log of assigned processors in postgresql
  curs.execute(createTable_processor_log)
  conn.commit()
  
  # create output spatial feature in Postgresql
  curs.execute(createTable_sausageBuffer)
  conn.commit()
  
  # fetch list of successfully processed buffers, if any
  unprocessed_hexes = '''
    SELECT DISTINCT(hex_id)
    FROM parcel_dwellings p
    WHERE NOT EXISTS 
    (SELECT 1 FROM {table} s WHERE s.{id} = p.{id});
  '''.format(table = sausage_buffer_table,
             id = points_id.lower())
  curs.execute(unprocessed_hexes)

  # compile list of remaining hexes to process
  remaining_hex_list = [int(x[0]) for x in list(curs)]
  
  # Setup a pool of workers/child processes and split log output
  pool = multiprocessing.Pool(nWorkers)
  
  # Divide work by hexes
  pool.map(CreateSausageBufferFunction, remaining_hex_list, chunksize=1)
      
  # Create sausage buffer spatial index
  print("Creating sausage buffer spatial index... "),
  curs.execute("CREATE INDEX IF NOT EXISTS {0}_gix ON {0} USING GIST (geom);".format(sausage_buffer_table))
  conn.commit()
  print("Done.")
  
  print("Analyze the sausage buffer table to improve performance.")
  curs.execute("ANALYZE {};".format(sausage_buffer_table))
  conn.commit()
  print("Done.")
      
  # Create summary table of parcel id and area
  print("Creating summary table of points with no sausage (are they mostly non-urban?)... "),  
  curs.execute("DROP TABLE IF EXISTS no_sausage; CREATE TABLE no_sausage AS SELECT * FROM parcel_dwellings WHERE {0} NOT IN (SELECT {0} FROM {1});".format(points_id,sausage_buffer_table))
  conn.commit()    
  print("Done.")
  
  # output to completion log    
  script_running_log(script, task, start, locale)
  
  # clean up
  conn.close()
  try:
    for gdb in glob.glob(os.path.join(temp,"scratch_{}_*.gdb".format(study_region))):
      arcpy.Delete_management(gdb)
  except: 
    print("FRIENDLY REMINDER!!! Remember to delete temp gdbs to save space!")
    print("(there may be lock files preventing automatic deletion.)")