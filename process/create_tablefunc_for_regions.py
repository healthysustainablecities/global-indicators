# Script:  0_create_sql_db.py
# Purpose: Facilitate creation of a PostgreSQL database 
# Authors: Carl Higgs
# Context: Used to create database and related settings for creation of liveability indicators
#
### Successful completion will look something like the following:
## Please enter default PostgreSQL database details to procede with new database creation, or close terminal to abort.
## Database: postgres
## Username: postgres
## Password for user postgres on database postgres:
## Connecting to default database to action queries.
## Creating database li_melb_2016...  Done.
## Adding comment "Liveability indicator data for melb 2016."...  Done.
## Creating user python...  Done.
## Creating ArcSDE user arc_sde...  Done.
## Connecting to li_melb_2016.
## Creating PostGIS extension ...  Done.
## Process successfully completed.
## Processing complete (Task: Create region-specific liveability indicator database, users and ArcSDE connection file); duration: 0.29 minutes

import psycopg2
import time
import getpass
import sys
import os

# Import custom variables for National Liveability indicator process
#from config_ntnl_li_process import *

# simple timer for log file
start = time.time()
script = os.path.basename(sys.argv[0])
task = 'Create region-specific liveability indicator database users and ArcSDE connection file'



# INPUT PARAMETERS
# note: these are in general defined in and loaded from config_ntnl_li_process.py

# default database
print("Please enter default PostgreSQL database details to procede with new database creation, or close terminal to abort.")
admin_db   = raw_input("Database: ")    
admin_user_name = raw_input("Username: ")
admin_pwd = getpass.getpass("Password for user {} on database {}: ".format(admin_user_name, admin_db))

print('Creating TableFunc extension ... ')
for region in sys.argv[1:]:
    print("  - {}".format(region))
    db = "li_{}_2018".format(region)
    conn = psycopg2.connect(dbname=db, user=admin_user_name, password=admin_pwd)
    curs = conn.cursor()
    curs.execute('''CREATE EXTENSION IF NOT EXISTS tablefunc;''')
    conn.commit()

print("Done.")	
conn.close()
