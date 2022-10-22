'''
_create_ghs_population_vrt.py

Creates global virtual raster table files for Mollwiede and WGS84 GHS population raster dataset tiles

'''


import time
from sqlalchemy import create_engine,inspect
import geopandas as gpd
from osgeo import gdal
import rasterio
from rasterio.mask import mask
import psycopg2
from geoalchemy2 import Geometry, WKTElement
import numpy as np
from shapely.geometry import Polygon, MultiPolygon
from rasterstats import zonal_stats
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
    print("Interpolation of population data to hex grid and overall urban summary...")
    analyses = {
        hex_grid: {
            'id':'hex_id',
            'table':population_grid,
            'stats':'mean'
            # small gridded area average (approximates distrbution)
            }, 
        'urban_study_region': {
            'id':'study_region',
            'table':'urban_study_region_summary',
            'stats':'sum'
            # marginal sum for overall urban area
            }
        }
    for a in analyses:
        if not db_contents.has_table(analyses[a]['table']):
            analysis_area = gpd.GeoDataFrame.from_postgis(f'''SELECT * FROM {a}''',
                                                            engine, 
                                                            geom_col='geom')
            print(f"  - processing population zonal statistics for {a}...")
            result = zonal_stats(
                        analysis_area,
                        population_raster_projected,
                        stats=analyses[a]['stats'], 
                        all_touched=True,
                        geojson_out=True, 
                        nodata=population['raster_nodata']
                        )
            print("    - creating additional required fields...")
            df = gpd.GeoDataFrame.from_features(result)
            df.rename(columns={analyses[a]['stats']:'pop_est'},inplace=True)
            df['area_sqkm'] = df['geometry'].area/10**6
            df['pop_per_sqkm'] = df['pop_est'] / df['area_sqkm']
            # Create WKT geometry (postgis won't read shapely geometry)
            # Ensure all geometries are multipolygons (specifically - can't be mixed type; complicates things)
            df["geometry"] = [MultiPolygon([feature]) if type(feature) == Polygon else feature for feature in df["geometry"]]
            df['geom'] = df['geometry'].apply(lambda x: WKTElement(x.wkt, srid=srid))
            df.drop('geometry', 1, inplace=True)
            print(f"    - copying to postgis ({analyses[a]['table']})...")
            # Copy to project Postgis database
            df.to_sql(
                name=analyses[a]['table'], 
                con=engine, 
                if_exists='replace', 
                dtype={'geom': Geometry('MULTIPOLYGON', srid=srid)},
                index=False
                )
            # link with marginal intersection count and density
            print(f"    - estimating intersection count and density for {a}...")
            sql = f'''
            ALTER TABLE {analyses[a]['table']} ADD COLUMN IF NOT EXISTS intersection_count int;
            ALTER TABLE {analyses[a]['table']} ADD COLUMN IF NOT EXISTS intersections_per_sqkm double precision;
            CREATE INDEX IF NOT EXISTS clean_intersections_gix ON {intersections_table} USING GIST (geom);
            CREATE INDEX IF NOT EXISTS {analyses[a]['table']}_ix  ON {analyses[a]['table']} ("{analyses[a]['id']}");
            CREATE INDEX IF NOT EXISTS {analyses[a]['table']}_gix ON {analyses[a]['table']} USING GIST (geom);
            UPDATE {analyses[a]['table']} a
               SET intersection_count = b.intersection_count,
                   intersections_per_sqkm = b.intersection_count/a.area_sqkm
              FROM (SELECT h."{analyses[a]['id']}",
                           COUNT(i.*) intersection_count
                    FROM {analyses[a]['table']} h 
                    LEFT JOIN {intersections_table} i
                    ON st_contains(h.geom,i.geom) 
                    GROUP BY "{analyses[a]['id']}") b
            WHERE a."{analyses[a]['id']}" = b."{analyses[a]['id']}";
            '''
            engine.execute(sql)        
        else:
            print(f"    - population zonal statistics has already been procesed ({analyses[a]['table']}).")
    
    # grant access to the tables just created
    engine.execute(grant_query)
    # output to completion log					
    script_running_log(script, task, start, locale)
    engine.dispose()

if __name__ == '__main__':
    main()
