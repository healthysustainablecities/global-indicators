# Script:  17_parcel_indicators.py
# Purpose: Create dwelling indicators for national liveability project
# Author:  Carl Higgs 
# Date:    20180717

import time
import psycopg2 

from script_running_log import script_running_log

# Import custom variables for National Liveability indicator process
from _project_setup import *

# simple timer for log file
start = time.time()
script = os.path.basename(sys.argv[0])
task = 'create destination indicator tables'

# calculate weighted estimates for dwellings and people, based on development of following method (TO DO!)
sql = '''
SELECT SUM(dwellings_with_access)/SUM(dwelling) AS study_region_dwelling_proportion,
       SUM(people_with_access)/SUM(person)      AS study_region_person_proportion
FROM (SELECT mb_code_2016,  
             dwelling * AVG(ind) AS dwellings_with_access,
             dwelling,
             person   * AVG(ind) AS people_with_access,
             person
     FROM parcel_indicators p
     WHERE NOT EXISTS --filter out ids flagged for exclusion
       (SELECT 1 FROM excluded_parcels x WHERE x.gnaf_pid = p.gnaf_pid)
     GROUP BY mb_code_2016, p.dwelling, p.person) t;
'''.format(ind)


# output to completion log    
# script_running_log(script, task, start, locale)
# conn.close()
