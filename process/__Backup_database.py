# Script:  __Backup_database.txt
# Purpose: Directions for backing up an sql database
# Author:  Carl Higgs 
# Date:    13 August 2018
# 
#  This script outputs directions to manually back up your sql database.
#  This should be done 
#     - at the end of the project, 
#     - and at any earlier time where you/team feel(s)/agree(s) that backups should be made.
# 
#  1. Go to the data directory (e.g. D:\ntnl_li_2018_template\data )
#  2. Enter the following at the command prompt, replacing 'perth' and '2016' with the
#     relevant locale and timepoint for the study region database you are backing up


import os
import sys
import time
import datetime

from script_running_log import script_running_log

# Import custom variables for National Liveability indicator process
from config_ntnl_li_process import *

# simple timer for log file
start = time.time()
script = os.path.basename(sys.argv[0])
task = 'Output directions for backing up an sql database'
datetime = datetime.datetime.today().strftime('%Y%m%d_%H%M')
print('To back up your sql database, please do the following:')
print(' 1. Open a command prompt in the directory: {}'.format(locale_dir))
print(' 2. Run the following command:')
print('    pg_dump -U postgres -h localhost -W {db} > {db}_{datetime}.sql'.format(db = db,
                                                                                 datetime = datetime))
  
# output to completion log    
script_running_log(script, task, start, locale)
