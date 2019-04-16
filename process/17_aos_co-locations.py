# Purpose: Evaluate Euclidean buffer co-location of Areas of Open Space with other amenities within 100m
# Author:  Carl Higgs
# Date:    20180626

import time
import psycopg2
from script_running_log import script_running_log

# Import custom variables for National Liveability indicator process
from _project_setup import *

# simple timer for log file
start = time.time()
script = os.path.basename(sys.argv[0])
task = 'Co-locate Areas of Open Space (AOS) with other amenities'

# initiate postgresql connection
conn = psycopg2.connect(database=db, user=db_user, password=db_pwd)
curs = conn.cursor()

sql = '''
  ALTER TABLE open_space_areas DROP COLUMN IF EXISTS co_location_100m;
  ALTER TABLE open_space_areas ADD COLUMN co_location_100m jsonb;
  UPDATE open_space_areas o 
     SET co_location_100m  = t.co_location_100m
    FROM (SELECT aos_id, jsonb_agg(dest_class) AS co_location_100m
          FROM open_space_areas osa, study_destinations d 
         WHERE ST_DWithin(osa.geom,d.geom,100) 
            OR ST_Intersects(osa.geom,d.geom)
         GROUP BY aos_id) t 
   WHERE o.aos_id = t.aos_id
     AND t.co_location_100m IS NOT NULL;
'''


print(''' Example usage of co-location field:    
-- 
SELECT aos_id,
       jsonb_pretty(attributes) AS attributes,
       jsonb_pretty(co_location_100m) AS co_location_100m,
       -- evalaute for a specific destination class
       co_location_100m ? 'cafe_osm' AS near_cafe,
       -- evaluate for at least one of a range of destination classes
       co_location_100m ?| ARRAY['cafe_osm','restaurant_osm','pub_osm'] AS near_casual_eatery,
       -- evaluate for at least one of a range of destination classes where the domain field contains a particular string (wild card)
       co_location_100m ?| ARRAY(SELECT dest_name FROM dest_type WHERE domain LIKE '%Community, Culture and Leisure%') AS near_community_culture
 FROM open_space_areas o;
''')

start = time.time()
print("\nExecuting: {}".format(sql))
curs.execute(sql)
conn.commit()
print("Executed in {} mins".format((time.time()-start)/60))

# output to completion log    
script_running_log(script, task, start, locale)
conn.close()

