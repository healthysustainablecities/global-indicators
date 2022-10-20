"""

Export geopackage
~~~~~~~~~~~~~~~~~

"""

import geopandas as gpd
from geoalchemy2 import Geometry, WKTElement
from sqlalchemy import create_engine,inspect
import subprocess as sp
import os

from script_running_log import script_running_log

# Set up project and region parameters for GHSCIC analyses
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
    
    # Select a 1600 metre buffered study region
    # this will be use to restrict our features of interest to those which intersection
    # this layer on export to gpkg
    urban = gpd.GeoDataFrame.from_postgis(
        f'''SELECT geom FROM {buffered_study_region}''',
        engine)

    tables = ['aos_public_any_nodes_30m_line'  ,
              'aos_public_large_nodes_30m_line',
              'aos_public_osm'                 ,
             f'{intersections_table}'          ,
              'dest_type'                      ,
              'destinations'                   ,
              'edges'                          ,
              'nodes'                          ,
              f'{population_grid}'             ,
              'urban_sample_points'            ,
              'urban_study_region_summary'     ,
              'urban_covariates']
    if gtfs_feeds is not None:
        tables = tables + [gtfs['headway']]
      
    print("Copying input resource tables to geopackage..."),

    bbox =  '{} {} {} {}'.format(*urban.geometry.total_bounds)
    path = f'../data/study_region/{study_region}'
    
    try:
        os.remove(gpkg)
    except:
        pass
    
    for table in tables:
        print(f" - {table}")
        command = (
                   f'ogr2ogr -update -overwrite -lco overwrite=yes -f GPKG {gpkg} '
                   f'PG:"host={db_host} user={db_user} dbname={db} password={db_pwd}" '
                   f'  {table} '
                   f' -spat {bbox} '
                    )
        sp.call(command, shell=True)     
    print(" Done.")
    
    # # output to completion log					
    script_running_log(script, task, start, locale)
    engine.dispose()
    
if __name__ == '__main__':
    main()