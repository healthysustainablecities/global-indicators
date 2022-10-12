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
import json
from shapely.geometry import Polygon, MultiPolygon
from rasterstats import zonal_stats

from script_running_log import script_running_log

# Import custom variables for National Liveability indicator process
from _project_setup import *

def main():
    # simple timer for log file
    start = time.time()
    script = os.path.basename(sys.argv[0])
    task = 'Create population grid excerpt for city'
    engine = create_engine(f"postgresql://{db_user}:{db_pwd}@{db_host}/{db}")
    db_contents = inspect(engine)
    
    # population raster set up 
    population_folder = '../data/GHS'
    p = 'WGS84'
    clipping_boundary = gpd.GeoDataFrame.from_postgis(
        f'''SELECT geom FROM {buffered_study_region}''', 
        engine, 
        geom_col='geom' 
        )   
       
    # construct virtual raster table
    vrt = os.path.join(population_folder,f'ghs_{p}.vrt')
    population_raster_clipped   = os.path.join(locale_dir,f'ghs_{population["year_target"]}_{p}_{locale}.tif')
    population_raster_projected = os.path.join(locale_dir,f'ghs_{population["year_target"]}_{p}_{locale}_{srid}.tif')
    pop_feature = f'pop_ghs_{population["year_target"]}'
    print("Global population dataset..."),
    if not os.path.isfile(vrt):
        tif_folder = f'../data/GHS/{p}'
        tif_files = [os.path.join(tif_folder,file) for file in os.listdir(tif_folder) if os.path.splitext(file)[-1] == '.tif']
        gdal.BuildVRT(vrt, tif_files)
        print(f"  has now been indexed ({vrt}).")
    else:
        print(f"  has already been indexed ({vrt}).")
    print("Population data clipped to region..."),
    if not os.path.isfile(population_raster_clipped):
        # extract study region boundary in projection of tiles
        clipping = clipping_boundary.to_crs(population['epsg'])
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
                      new_crs = f'EPSG:{srid}')   
        print(f"  has now been created ({population_raster_projected}).")
    else:
        print(f"  has already been created ({population_raster_projected}).")
    print("Interpolation of population data to hex grid...")
    analysis_area = gpd.GeoDataFrame.from_postgis(f'''SELECT * FROM {hex_grid_250m}''',
                                                    engine, 
                                                    geom_col='geom', 
                                                    index_col='hex_id')
    print("  - processing population zonal statistics...")
    if not db_contents.has_table(pop_feature):
        result = zonal_stats(analysis_area,population_raster_projected,stats=population['raster_statistic'], all_touched=True,geojson_out=True, nodata=population['raster_nodata'])
        print("  - creating additional required fields...")
        hexpop = gpd.GeoDataFrame.from_features(result)
        hexpop.rename(columns={population['raster_statistic']:'pop_est'},inplace=True)
        # hexpop.pop_est = hexpop.pop_est.astype(np.int64) # this doesn't work
        hexpop['area_sqkm'] = hexpop['geometry'].area/10**6
        hexpop['pop_per_sqkm'] = hexpop['pop_est'] / hexpop['area_sqkm']
        # Create WKT geometry (postgis won't read shapely geometry)
        hexpop["geometry"] = [MultiPolygon([feature]) if type(feature) == Polygon else feature for feature in hexpop["geometry"]]
        hexpop['geom'] = hexpop['geometry'].apply(lambda x: WKTElement(x.wkt, srid=srid))
        hexpop.drop('geometry', 1, inplace=True)
        # hexpop.drop('mean', 1, inplace=True)
        # Ensure all geometries are multipolygons (specifically - can't be mixed type; complicates things)
        print(f"  - copying to postgis ({pop_feature})...")
        # Copy to project Postgis database
        hexpop.to_sql(pop_feature, engine, if_exists='replace', index=True, dtype={'geom': Geometry('MULTIPOLYGON', srid=srid)})
    else:
        print(f"    - hex grid with population zonal statistics has already been procesed ({pop_feature}).")
    print("Associating hex grid with intersection counts...")
    sql = f'''
    ALTER TABLE {pop_feature} ADD COLUMN IF NOT EXISTS intersection_count int;
    ALTER TABLE {pop_feature} ADD COLUMN IF NOT EXISTS intersections_per_sqkm double precision;
    CREATE INDEX IF NOT EXISTS clean_intersections_gix ON {intersections_table} USING GIST (geom);
    UPDATE {pop_feature} a
       SET intersection_count = b.intersection_count,
           intersections_per_sqkm = b.intersection_count/a.area_sqkm
      FROM (SELECT h.index,
                   COUNT(i.*) intersection_count
            FROM {pop_feature} h 
            LEFT JOIN {intersections_table} i
            ON st_contains(h.geom,i.geom) 
            GROUP BY h.index) b
    WHERE a.index = b.index;
    '''
    engine.execute(sql)
        
    # grant access to the tables just created
    engine.execute(grant_query)
    # output to completion log					
    script_running_log(script, task, start, locale)
    engine.dispose()

if __name__ == '__main__':
    main()
