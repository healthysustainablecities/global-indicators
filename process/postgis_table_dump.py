# Script:  postgis_table_dump.py
# Purpose: Output table
# Author:  Carl Higgs 
# Date:    3 August 2018

# Import custom variables for National Liveability indicator process
import psycopg2 
from config_ntnl_li_process import *

conn = psycopg2.connect(database=db, user=db_user, password=db_pwd)
curs = conn.cursor()

localise_names = '''
ALTER TABLE li_map_sa1      RENAME TO li_map_sa1_{locale}_{year};
ALTER TABLE li_map_ssc      RENAME TO li_map_ssc_{locale}_{year};      
ALTER TABLE li_map_lga      RENAME TO li_map_lga_{locale}_{year};      
ALTER TABLE ind_description RENAME TO ind_description_{locale}_{year}; 
ALTER TABLE boundaries_sa1  RENAME TO boundaries_sa1_{locale}_{year};  
ALTER TABLE boundaries_ssc  RENAME TO boundaries_ssc_{locale}_{year};  
ALTER TABLE boundaries_lga  RENAME TO boundaries_lga_{locale}_{year};  
CREATE TABLE urban_sos_{locale}_{year} AS SELECT sos_name_2 AS sos_name_2016, ST_Transform(a.geom,4326) AS geom FROM  main_sos_2016_aust a, gccsa_2016 b WHERE ST_Intersects(a.geom,b.geom) AND sos_name_2 IN('Major Urban','Other Urban');'''.format(locale = locale.lower(), year = year)

curs.execute(localise_names)
conn.commit()
  
print("Can you please run the following from the command prompt in the following directory: {local_dir}".format(local_dir = local_dir))
print('''
pg_dump -U postgres -h localhost -W  -t "li_map_sa1_{locale}_{year}" -t "li_map_ssc_{locale}_{year}" -t "li_map_lga_{locale}_{year}" -t "ind_description_{locale}_{year}" -t "boundaries_sa1_{locale}_{year}" -t "boundaries_ssc_{locale}_{year}" -t "boundaries_lga_{locale}_{year}" -t "urban_sos_{locale}_{year}" {db} > li_map_{db}.sql
'''.format(locale = locale.lower(), year = year,db = db))

print('''
Also, can you send the following line of text to Carl please?
psql observatory < {locale_dir}/li_map_{db}.sql postgres
'''.format(locale_dir = locale_dir,db = db))