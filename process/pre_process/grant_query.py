# Script:  grant_query.py
# Purpose: -- If no argument is given, this script prints out a grant query
#          which may be run manually (
#          ie. to allow python and arc_sde users to modify tables created by
#          the admin user.
#          -- If a study region is specified, admin connection details are 
#          requested and an admin connection is made to that database 
#          in order to execute the query
# Author:  Carl Higgs
# Date:    20190208

# Import custom variables for National Liveability indicator process
import sys
  
grant_query = '''
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO arc_sde;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO arc_sde;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO python;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO python;
'''
if len(sys.argv) < 2:
  print(grant_query)
else:
  import psycopg2
  import time
  import getpass
  import os
  print("Please enter PostgreSQL admin details to grant all privileges to python and arc_sde users")
  admin_db   = raw_input("Database: ")    
  admin_user_name = raw_input("Username: ")
  admin_pwd = getpass.getpass("Password for user {} on database {}: ".format(admin_user_name, admin_db))
  print("Executing grant query and ensuring tablefunc extension is created...")
  for region in sys.argv[1:]:
    print("  - {}".format(region))
    db = "li_{}_2018".format(region)
    conn = psycopg2.connect(dbname=db, user=admin_user_name, password=admin_pwd)
    curs = conn.cursor()
    curs.execute('''CREATE EXTENSION IF NOT EXISTS tablefunc;''')
    conn.commit()
    curs.execute(grant_query)
    conn.commit()
  print("Done.")