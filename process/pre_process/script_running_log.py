# Script:  script_running_log.py
# Purpose: log completion to sql
# Author:  Carl Higgs
# Date:    20181009

# Note: This script assumes the specified postgresql database has already been created.
import os
import sys
import time
import psycopg2
# Import custom variables for National Liveability indicator process
from _project_setup import db,db_user,db_pwd,db_host,db_port

# Define script logging to study region database function
def script_running_log(script = '', task = '', start = '', prefix = ''):
  # Initialise postgresql connection
  conn = psycopg2.connect(dbname=db, user=db_user, password=db_pwd, host = db_host,  port = db_port)
  curs = conn.cursor()  
  date_time = time.strftime("%Y%m%d-%H%M%S")
  duration = (time.time() - start)/60
  
  log_table = '''
       -- If log table doesn't exist, its created
       CREATE TABLE IF NOT EXISTS script_log
       (
       script varchar,
       task varchar,
       datetime_completed varchar,
       duration_mins numeric
       );
       -- Insert completed script details
       INSERT INTO script_log VALUES ($${}$$,$${}$$,$${}$$,{});
       '''.format(script,task,date_time,duration)
  try:
    curs.execute(log_table)
    conn.commit()
    print('''Processing completed at {}\n- Task: {}\n- Duration: {:04.2f} minutes'''.format(date_time,task,duration))
  except:
    print("Error withoutput to script running log.  Has the database for this study region been created?")
    raise
  finally:
    conn.close()