'''
 -- Summarise destination counts and POS in Ha for hexes
'''

import time 
import psycopg2
from sqlalchemy import create_engine,inspect

from _project_setup import *
from script_running_log import script_running_log

def main():
    start = time.time()
    script = os.path.basename(sys.argv[0])
    task = 'Summarise destination counts and POS in Ha for hexes'
    conn = psycopg2.connect(database=db, user=db_user, password=db_pwd)
    curs = conn.cursor()
    sql = '''SELECT distinct(dest_name) FROM osm_destinations;'''
    curs.execute(sql)
    destinations = [x[0] for x in curs.fetchall()]
    for dest in destinations:
        sql = f'''
        ALTER TABLE pop_ghs_2015 ADD COLUMN IF NOT EXISTS count_{dest} int;
        UPDATE pop_ghs_2015 p
           SET count_{dest} = r.count
        FROM (SELECT h.index,
                     COUNT(d.geom) AS count
              FROM pop_ghs_2015 h,
              osm_destinations d
              WHERE dest_name = '{dest}'
                AND ST_Intersects(h.geom,d.geom)
              GROUP BY h.index) r
        WHERE p.index = r.index;    
        '''        
        curs.execute(sql)
        conn.commit()
    
    script_running_log(script, task, start, locale)
    conn.close()
        
if __name__ == '__main__':
    main()
