'''
 -- Summarise destination counts and POS in Ha for grid cells
'''

import time 
import pandas as pd
from sqlalchemy import create_engine,inspect

from _project_setup import *
from script_running_log import script_running_log

def main():
    start = time.time()
    script = os.path.basename(sys.argv[0])
    task = 'Summarise destinations and public open space'
    date_yyyymmdd = time.strftime("%d%m%Y")

    engine = create_engine(f"postgresql://{db_user}:{db_pwd}@{db_host}/{db}")
    sql = '''SELECT distinct(dest_name) FROM destinations;'''
    result = engine.execute(sql)
    destinations = [x[0] for x in result.fetchall()]
    result.close()
    for dest in destinations:
        sql = f'''
        ALTER TABLE {population_grid} ADD COLUMN IF NOT EXISTS count_{dest} int;
        UPDATE {population_grid} p
           SET count_{dest} = r.count
        FROM (SELECT h.id,
                     COUNT(d.geom) AS count
              FROM {population_grid} h,
              destinations d
              WHERE dest_name = '{dest}'
                AND ST_Intersects(h.geom,d.geom)
              GROUP BY h.id) r
        WHERE p.id = r.id;    
        '''        
        engine.execute(sql)
    
    count_sql = f'''
    DROP TABLE IF EXISTS urban_dest_summary;
    CREATE TABLE IF NOT EXISTS urban_dest_summary AS
    SELECT a."study_region", 
           t.dest_name_full, 
           t.count, 
           a.pop_est,
           a.area_sqkm, 
           a.pop_per_sqkm,
           t.count/a.area_sqkm AS dest_per_sqkm,
           t.count/a.area_sqkm/(pop_est/10000) AS dest_per_sqkm_per_10kpop
    FROM urban_study_region_summary a, 
         (SELECT d.dest_name_full, 
                 COUNT(d.*) count 
            FROM destinations d,
                 urban_study_region_summary c
        WHERE ST_Intersects(d.geom, c.geom)
        GROUP BY dest_name_full ) t
    ;
    SELECT * FROM urban_dest_summary;
    '''
                                                             
    df = pd.read_sql(count_sql, con=engine, index_col=None)
    df.to_csv(f'./../data/study_region/{study_region}/osm_audit_{locale}_{date_yyyymmdd}.csv')

    script_running_log(script, task, start, locale)
    engine.dispose()
        
if __name__ == '__main__':
    main()
