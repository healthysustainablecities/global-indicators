"""

Database creation
~~~~~~~~~~~~~~~~~

::

    Script:  03_create_osm_resources.py
    Purpose: Create pedestrian street networks for specified city (2019)
    
"""

import time
import os
import sys
import subprocess as sp
from datetime import datetime
import psycopg2 
from script_running_log import script_running_log
# Import custom variables for National Liveability indicator process
from _project_setup import *

def main():
    # simple timer for log file
    start = time.time()
    script = os.path.basename(sys.argv[0])
    task = 'Except and collate OSM resources for study region'
    
    conn = psycopg2.connect(database=db, user=db_user, password=db_pwd, host=db_host,port=db_port)
    curs = conn.cursor()
    
    # create polygon boundary .poly file for extracting OSM             
    print("Create poly file, using command: "),
    locale_poly = f'poly_{db}.poly'
    feature = f'PG:"dbname={db} host={db_host} port={db_port} user={db_user} password={db_pwd}" {buffered_study_region}'
    command = f'python ogr2poly.py {feature} -f "db"'
    print(command)
    sp.call(command, shell=True)
    command = f'mv {locale_poly} {locale_dir}/{locale_poly}'
    print(f'\t{command}')
    sp.call(command, shell=True)
    print("Done.")
    
    # Extract OSM
    print("Extract OSM for studyregion"),
    if os.path.isfile(f'{locale_dir}/{osm_region}'):
      print(f'...\r\n.osm file "{locale_dir}/{osm_region}" already exists')
    else:
      print(" using command:")
      command = f'osmconvert "{osm_data}" -B="{locale_dir}/{locale_poly}" -o="{locale_dir}/{osm_region}"'
      print(command)
      sp.call(command, shell=True)
    print('Done.')
    
    # import buffered study region OSM excerpt to pgsql, 
    # check if OSM excerpt has previously been imported
    curs.execute(f'''SELECT 1 WHERE to_regclass('public.{osm_prefix}_line') IS NOT NULL;''')
    res = curs.fetchone()
    if res is None:
        print("Copying OSM excerpt to pgsql..."),
        command = f'osm2pgsql -U {db_user} -l -d {db} --host {db_host} --port {db_port} {locale_dir}/{osm_region} --hstore --prefix {osm_prefix}'
        print(command)
        sp.call(command, shell=True)                           
        print("Done.")
        
        required_fields_list = df_os.loc['os_required'].criteria.split(',')
        
        for shape in ['line','point','polygon','roads']:
            # Define tags for which presence of values is suggestive of some kind of open space 
            # These are defined in the _project_configuration worksheet 'open_space_defs' under the 'required_tags' column.
            required_tags = '\n'.join([(
                f'ALTER TABLE {osm_prefix}_{shape} ADD COLUMN IF NOT EXISTS "{x}" varchar;'
                ) for x in required_fields_list]
                )
            sql = [f'''
            -- Add geom column to polygon table, appropriately transformed to project spatial reference system
            ALTER TABLE {osm_prefix}_{shape} ADD COLUMN geom geometry; 
            UPDATE {osm_prefix}_{shape} SET geom = ST_Transform(way,{srid}); 
            CREATE INDEX {osm_prefix}_{shape}_idx ON {osm_prefix}_{shape} USING GIST (geom);
            ''',
            f'''
            -- Add other columns which are important if they exists, but not important if they don't
            -- --- except that there presence is required for ease of accurate querying.
            {required_tags}''']
            for query in sql:
                query_start = time.time()
                print(f"\nExecuting: {query}")
                curs.execute(query)
                conn.commit()
                duration = (time.time()-query_start)/60
                print(f"Executed in {duration} mins")
            
        curs.execute(grant_query)
        conn.commit()    
    else:
        print("It appears that OSM data has already been imported for this region.")
        
    script_running_log(script, task, start)
    
    # clean up
    conn.close()

if __name__ == '__main__':
    main()