# Script:  count_parcels_in_hexes.py
# Purpose: Summarises parcel count within hexes and outputs this to an sql table
#          'hex_parcels'
#          Parcels are now pre-associated w/ hexes so can be iterated over directly.
#          Previously this exported to a csv file parcels_in_hexes.csv

import pandas
import time
import psycopg2 
import numpy as np

from script_running_log import script_running_log

# Import custom variables for National Liveability indicator process
from _project_setup import *

# simple timer for log file
start = time.time()
script = os.path.basename(sys.argv[0])
task = 'count points in hexes'
print("Commencing task: {} at {}".format(task,time.strftime("%Y%m%d-%H%M%S")))

# ArcGIS environment settings
arcpy.env.workspace = gdb_path
arcpy.env.overwriteOutput = True 

## specify locations
points = 'parcel_dwellings'

## Log file details (including header row)
log_table = 'hex_parcels'

conn = psycopg2.connect(database=db, 
                        user=db_user,
                        password=db_pwd)
curs = conn.cursor()

def bin_unique_values(table, field):
  # returns list of (value,count) tuples
  data = arcpy.da.TableToNumPyArray(table, [field])
  y = np.bincount(np.asarray([x[0] for x in data]))
  ii = np.nonzero(y)[0]
  return  zip(ii,y[ii])
  
# Define log file write method
def writeLog(hex,parcelCount,cumfreq,percentile):
  # print to screen regardless
  if cumfreq == 0:
    createTable_log = '''
      CREATE TABLE {} 
        (hex integer PRIMARY KEY, 
        parcel_count integer NOT NULL, 
        cumfreq integer NOT NULL, 
        percentile double precision);
        '''.format(log_table)
    curs.execute("DROP TABLE IF EXISTS %s;" % log_table)
    conn.commit()
    
    curs.execute(createTable_log)
    conn.commit()
 
    print('{:>10}  {:>10} {:>10} {:>10}'.format('hex','parcelCount','cumfreq','percentile'))
 
  else:
    curs.execute("INSERT INTO {} VALUES ({},{},{},{})".format(log_table,hex,parcelCount,cumfreq,percentile))
    conn.commit()
    
    print("\b"*50),
    print('{:9.0f}    {:9.0f} {:10.0f} {:10.2f} '.format(hex,parcelCount,cumfreq,percentile)),
      
# OUTPUT PROCESS
try:    
  # Prepare to loop over points within polygons
  arcpy.MakeFeatureLayer_management (parcel_dwellings, "pointsLayer")
  
  denominator = int(arcpy.GetCount_management('pointsLayer').getOutput(0))
  cumfreq = 0

  # initialise log timer
  writeLog(0,0,0,0)
  
  # iterate over values of hexes
  hex_freq = bin_unique_values('pointsLayer', 'HEX_ID')
  for hex in hex_freq:  
    hex_id = hex[0]
    hex_count = hex[1]
    cumfreq += hex_count 
    percentile = (cumfreq/float(denominator))*100
    writeLog(hex_id,hex_count, cumfreq, round(percentile,2))

  print("\n")    

finally:        
  conn.close()
script_running_log(script, task, start, locale)
