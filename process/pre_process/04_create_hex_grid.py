"""

Create sample points and hex grid
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

::

    Script:  05_create_sample_points.py
    Purpose: Create hex grid and sample points

"""

import time
from sqlalchemy import create_engine,inspect,inspect
import psycopg2
from _utils import hex_function

from script_running_log import script_running_log

# Set up project and region parameters for GHSCIC analyses
from _project_setup import *

def main():
    # simple timer for log file
    start = time.time()
    script = os.path.basename(sys.argv[0])
    task = 'Create hex grid and sample points'
    
    conn = psycopg2.connect(database=db, user=db_user, password=db_pwd, host=db_host,port=db_port)
    curs = conn.cursor()
    
    engine = create_engine(f"postgresql://{db_user}:{db_pwd}@{db_host}/{db}")
    db_contents = inspect(engine)
   
    if not inspect(engine).has_table(hex_grid):  
        # Create hex grid using algorithm from Hugh Saalmans (@minus34) under Apache 2 licence
        # https://github.com/minus34/postgis-scripts/blob/master/hex-grid/create-hex-grid-function.sql
        curs.execute(hex_function)
        conn.commit()
        
        # create hexes with some additional offsetting to ensure complete study region coverage
        sql = f'''
        CREATE TABLE IF NOT EXISTS {hex_grid} AS
        SELECT row_number() OVER () AS hex_id, geom
          FROM (
          SELECT hex_grid({hex_area_km2}::float, 
                          ST_XMin(geom)-{hex_diag}, 
                          ST_YMin(geom)-{hex_diag}, 
                          ST_XMax(geom)+{hex_diag}, 
                          ST_YMax(geom)+{hex_diag}, 
                          {srid}, 
                          {srid}, 
                          {srid}) geom, geom AS old_geom
        FROM {buffered_study_region}) t
        WHERE ST_Intersects(geom,old_geom);
        CREATE UNIQUE INDEX IF NOT EXISTS {hex_grid}_idx ON {hex_grid} (hex_id);
        CREATE INDEX IF NOT EXISTS {hex_grid}_geom_idx ON {hex_grid} USING GIST (geom);
        '''     
        
        engine.execute(sql)     
    else:
        print(f"  - The table {hex_grid} has already been processed.") 
 
    # grant access to the tables just created
    engine.execute(grant_query)
    
    # output to completion log					
    script_running_log(script, task, start, locale)
    
    conn.close()

if __name__ == '__main__':
    main()