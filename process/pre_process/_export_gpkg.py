"""

Export geopackage
~~~~~~~~~~~~~~~~~

"""

import geopandas as gpd
from geoalchemy2 import Geometry, WKTElement
import folium
from folium import plugins
import branca
from sqlalchemy import create_engine
import psycopg2
import numpy as np
import json

from script_running_log import script_running_log

# Import custom variables for National Liveability indicator process
from _project_setup import *

def main():
    # simple timer for log file
    start  = time.time()
    script = os.path.basename(sys.argv[0])
    task = 'Export geopackage'
    
    engine = create_engine("postgresql://{user}:{pwd}@{host}/{db}".format(user = db_user,
                                                                          pwd  = db_pwd,
                                                                          host = db_host,
                                                                          db   = db))  
    # Oddities with primary keys of destination and sample points mean that we need to create_engine
    # new tables for export
    sql = '''
        CREATE TABLE IF NOT EXISTS destinations AS SELECT * FROM osm_destinations;
    '''
    engine.execute(sql)
    
    # Select a 1600 metre buffered study region
    # this will be use to restrict our features of interest to those which intersection
    # this layer on export to gpkg
    urban_region = gpd.GeoDataFrame.from_postgis('''SELECT ST_Buffer(geom,1600) geom FROM urban_study_region''',engine)
    
   
    tables = ['aos_public_any_nodes_30m_line',
              'aos_public_large_nodes_30m_line',
              'aos_public_osm',
              'clean_intersections_12m'      ,
              'dest_type'                    ,
              'destinations'                 ,
              'pop_ghs_2015'                 ,
              'urban_sample_points'          ,
              'urban_study_region'           ]
    
    print("Copying input resource tables to geopackage..."),
    command = (
                'ogr2ogr -overwrite -f GPKG {path}/{output_name}_1600m_buffer.gpkg '
                'PG:"host={host} user={user} dbname={db} password={pwd}" '
                '  {tables}'
                ' -spat {bbox}'
                ).format(output_name = '{}'.format(study_region),
                         bbox =  '{} {} {} {}'.format(*urban_region.geometry.total_bounds),
                         path = f'../data/study_region/{study_region}',
                         host = db_host,
                         user = db_user,
                         pwd = db_pwd,
                         db = db,
                         tables =  ' '.join(tables))
    sp.call(command, shell=True)     
    print(" Done.")
    
    # # output to completion log					
    script_running_log(script, task, start, locale)
    engine.dispose()
    
if __name__ == '__main__':
    main()