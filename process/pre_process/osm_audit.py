# OSM Audit  - Lancet series

import time
import psycopg2
import pandas
from sqlalchemy import create_engine

from script_running_log import script_running_log

# Import custom variables for National Liveability indicator process
from _project_setup import *
from datetime import datetime
today = datetime.today().strftime('%Y-%m-%d')
sql = ''' 
SELECT city, 
       dest_name_full, 
       count, 
       area_sqkm, 
       count/area_sqkm AS dest_per_km2 
FROM city, 
     (SELECT dest_name_full, 
             SUM(count) count 
        FROM dest_type 
    GROUP BY dest_name_full) t
;
'''


cities = ['abuja','lagos','maiduguri','mexico_city','baltimore','phoenix','seattle','sao_paulo','hong_kong','chennai','bangkok','hanoi','graz','ghent','bern','olomouc','cologne','odense','barcelona','valencia','vic','belfast','lisbon','adelaide','melbourne','sydney','auckland']
# connect to the PostgreSQL server
for locale in cities:
    engine = create_engine("postgresql://{user}:{pwd}@{host}/{db}".format(user = db_user,
                                                                          pwd  = db_pwd,
                                                                          host = db_host,
                                                                          db   = 'li_{}_2019'.format(locale)))
    df = pandas.read_sql(sql, con=engine, index_col=None)
    if cities.index(locale)==0:
        results = df
    else:
        results  = results.append(df)

results.to_csv(f'osm_audit_{today}.csv')