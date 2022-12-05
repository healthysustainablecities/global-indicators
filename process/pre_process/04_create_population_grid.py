'''
_create_ghs_population_vrt.py

Creates global virtual raster table files for Mollwiede and WGS84 GHS population raster dataset tiles

'''

import time
from sqlalchemy import create_engine,inspect
import geopandas as gpd
from osgeo import gdal
import subprocess as sp
from _utils import reproject_raster

from script_running_log import script_running_log

# Set up project and region parameters for GHSCIC analyses
from _project_setup import *

def main():
    # simple timer for log file
    start = time.time()
    script = os.path.basename(sys.argv[0])
    task = 'Create population grid excerpt for city'
    engine = create_engine(f"postgresql://{db_user}:{db_pwd}@{db_host}/{db}")
    db_contents = inspect(engine)
    
    # population raster set up 
    population_folder = population['data_dir']
    population_stub = f'{locale_dir}/{population_grid}_{locale}'
    clipping_boundary = gpd.GeoDataFrame.from_postgis(
        f'''SELECT geom FROM {buffered_study_region}''', 
        engine, 
        geom_col='geom' 
        )   
       
    # construct virtual raster table
    vrt = f'{population["data_dir"]}/{population_grid}_{population["crs"]}.vrt'
    population_raster_clipped   = f'{population_stub}_{population["crs"]}.tif'
    population_raster_projected = f'{population_stub}_{srid}.tif'
    print("Global population dataset..."),
    if not os.path.isfile(vrt):
        tif_folder = population["data_dir"]
        tif_files = [os.path.join(tif_folder,file) for file in os.listdir(tif_folder) if os.path.splitext(file)[-1] == '.tif']
        gdal.BuildVRT(vrt, tif_files)
        print(f"  has now been indexed ({vrt}).")
    else:
        print(f"  has already been indexed ({vrt}).")
    print("Population data clipped to region..."),
    if not os.path.isfile(population_raster_clipped):
        # extract study region boundary in projection of tiles
        clipping = clipping_boundary.to_crs(population['crs'])
        # get clipping boundary values in required order for gdal translate
        bbox = list(clipping.bounds[['minx','maxy','maxx','miny']].values[0]) 
        # bbox = list(clipping.bounds.values[0]) 
        ds = gdal.Translate(population_raster_clipped, vrt, projWin = bbox)
        ds = None
        print(f"  has now been created ({population_raster_clipped}).")
    else:
        print(f"  has already been created ({population_raster_clipped}).")
    print("Population data projected for region..."),
    if not os.path.isfile(population_raster_projected):
        # reproject and save the re-projected clipped raster
        # (see config file for reprojection function)
        reproject_raster(inpath = population_raster_clipped, 
                      outpath = population_raster_projected, 
                      new_crs = crs)   
        print(f"  has now been created ({population_raster_projected}).")
    else:
        print(f"  has already been created ({population_raster_projected}).")
    print("Population data grid for analysis..."),
    if not db_contents.has_table(population_grid):     
        # import raster to postgis and vectorise, as per http://www.brianmcgill.org/postgis_zonal.pdf
        command = (
            f"raster2pgsql -d -s {srid} -c -I -Y "
            f"-N {population['raster_nodata']} "
            f"-t  1x1 {population_raster_projected} {population_grid} "
            f"| PGPASSWORD={db_pwd} psql -U postgres -h {db_host} -d {db} "
            ">> /dev/null"
        )
        sp.call(command, shell=True)
        sql = f"""
        ALTER TABLE {population_grid} DROP COLUMN rid;
        ALTER TABLE {population_grid} ADD grid_id bigserial;
        ALTER TABLE {population_grid} ADD COLUMN IF NOT EXISTS pop_est int;
        ALTER TABLE {population_grid} ADD COLUMN IF NOT EXISTS geom geometry;
        ALTER TABLE {population_grid} ADD COLUMN IF NOT EXISTS area_sqkm float;
        ALTER TABLE {population_grid} ADD COLUMN IF NOT EXISTS pop_per_sqkm float;
        ALTER TABLE {population_grid} ADD COLUMN IF NOT EXISTS intersection_count int;
        ALTER TABLE {population_grid} ADD COLUMN IF NOT EXISTS intersections_per_sqkm float;
        DELETE FROM {population_grid} WHERE (ST_SummaryStats(rast)).sum IS NULL;
        UPDATE      {population_grid} SET geom = ST_ConvexHull(rast);
        CREATE INDEX {population_grid}_ix  ON {population_grid} (grid_id); 
        CREATE INDEX {population_grid}_gix ON {population_grid} USING GIST(geom); 
        DELETE FROM {population_grid}
            WHERE {population_grid}.grid_id NOT IN (
                SELECT p.grid_id
                FROM 
                    {population_grid} p, 
                    {buffered_study_region} b 
                WHERE ST_Intersects (
                    p.geom,
                    b.geom
                )
            );
        UPDATE      {population_grid} SET area_sqkm = ST_Area(geom)/10^6;
        UPDATE      {population_grid} SET pop_est = (ST_SummaryStats(rast)).sum;
        UPDATE      {population_grid} SET pop_per_sqkm = pop_est/area_sqkm;
        CREATE INDEX IF NOT EXISTS clean_intersections_gix ON {intersections_table} USING GIST (geom);
        UPDATE {population_grid} a
           SET intersection_count = b.intersection_count,
               intersections_per_sqkm = b.intersection_count/a.area_sqkm
          FROM (SELECT h."grid_id",
                       COUNT(i.*) intersection_count
                FROM {population_grid} h 
                LEFT JOIN {intersections_table} i
                ON st_contains(h.geom,i.geom) 
                GROUP BY "grid_id") b
        WHERE a."grid_id" = b."grid_id";  
        ALTER TABLE {population_grid} DROP COLUMN rast;
        """     
        with engine.begin() as connection:
            connection.execute(sql)            
        # urban summary
        sql = f"""
        ALTER TABLE urban_study_region ADD COLUMN IF NOT EXISTS area_sqkm double precision;
        ALTER TABLE urban_study_region ADD COLUMN IF NOT EXISTS pop_est int;
        ALTER TABLE urban_study_region ADD COLUMN IF NOT EXISTS pop_per_sqkm int;
        ALTER TABLE urban_study_region ADD COLUMN IF NOT EXISTS intersection_count int;
        ALTER TABLE urban_study_region ADD COLUMN IF NOT EXISTS intersections_per_sqkm double precision;
        UPDATE urban_study_region a
            SET 
                area_sqkm = b.area_sqkm,
                pop_est = b.pop_est,
                pop_per_sqkm = b.pop_est/b.area_sqkm,
                intersection_count = b.intersection_count,
                intersections_per_sqkm = b.intersection_count/b.area_sqkm
            FROM (
                SELECT
                    "study_region",
                    ST_Area(u.geom)/10^6 area_sqkm,
                    SUM(p.pop_est) pop_est,
                    SUM(p.intersection_count) intersection_count
                FROM urban_study_region u, 
                     {population_grid} p
                WHERE ST_Intersects(u.geom,p.geom) 
                GROUP BY u."study_region",u.geom
                ) b
            WHERE a.study_region = b.study_region;
        """
        with engine.begin() as connection:
            connection.execute(sql)
    else:
        print(f"    - {population_grid} has already been procesed.")
    
    # grant access to the tables just created
    with engine.begin() as connection:
        connection.execute(grant_query)
    # output to completion log					
    script_running_log(script, task, start, locale)
    engine.dispose()

if __name__ == '__main__':
    main()
