# OSM Audit  - Lancet series
import time
from sqlalchemy import create_engine
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
    task = 'Summarise OSM destination resources for city'

    date_yyyymmdd = time.strftime("%d%m%Y")
    # population raster set up 
    population_folder = '../data/GHS'
    # projections = {'Mollwiede':54009,'WGS84':4326}
    projections = {'WGS84':4326}
    ghs_year = 2015   
    region_sql = '''
    SELECT "Study region" study_region, 
           geom
    FROM urban_study_region
    '''
    count_sql = '''
    DROP TABLE IF EXISTS urban_dest_summary;
    CREATE TABLE IF NOT EXISTS urban_dest_summary AS
    SELECT a.study_region, 
           t.dest_name_full, 
           t.count, 
           a.urban_pop_est,
           a.area_sqkm, 
           a.pop_per_sqkm,
           t.count/a.area_sqkm AS dest_per_sqkm,
           t.count/a.area_sqkm/(urban_pop_est/10000) AS dest_per_sqkm_per_10kpop
    FROM urban_study_region_pop a, 
         (SELECT d.dest_name_full, 
                 COUNT(d.*) count 
            FROM osm_destinations d,
                 urban_study_region_pop c
        WHERE ST_Intersects(d.geom, c.geom)
        GROUP BY dest_name_full ) t
    ;
    SELECT * FROM urban_dest_summary;
    '''

    if locale != 'vic':
        print(locale)
        xls = pandas.ExcelFile(os.path.join(cwd,'_project_configuration.xlsx'))
        df_local = pandas.read_excel(xls, 'region_settings',index_col=0)
        df_local[locale] = df_local[locale].fillna('')
        for var in [x for x in  df_local.index.values]:
            globals()[var] = df_local.loc[var][locale]
        study_region = '{}_{}_{}'.format(locale,region,year).lower()
        # region specific output locations
        locale_dir = os.path.join(folder_path,'study_region','{}'.format(study_region))
        buffered_study_region = '{}_{}{}'.format(study_region,study_buffer,units)
        engine = create_engine(f"postgresql://{db_user}:{db_pwd}@{db_host}/{db}")
        clipping_boundary = gpd.GeoDataFrame.from_postgis('''SELECT geom FROM {table}'''.format(table = buffered_study_region), engine, geom_col='geom' )   
        for p in projections:
            # construct virtual raster table
            vrt = os.path.join(population_folder,f'ghs_{p}.vrt')
            population_raster_clipped   = os.path.join(locale_dir,f'ghs_{ghs_year}_{p}_{locale}.tif')
            population_raster_projected = os.path.join(locale_dir,f'ghs_{ghs_year}_{p}_{locale}_{srid}.tif')
            pop_feature = f'pop_ghs_{ghs_year}'
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
                clipping = clipping_boundary.to_crs({'init':'epsg:{}'.format(projections[p])})
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
                              new_crs = 'EPSG:{}'.format(srid))   
                print(f"  has now been created ({population_raster_projected}).")
            else:
                print(f"  has already been created ({population_raster_projected}).")
            print("Interpolation of population data to urban area...")
            analysis_area = gpd.GeoDataFrame.from_postgis(region_sql,
                                                            engine, 
                                                            geom_col='geom')
            print("  - processing population zonal statistics...")
            pop_feature = "urban_study_region_pop"
            if not engine.has_table(pop_feature):
                result = zonal_stats(analysis_area,population_raster_projected,stats="sum", all_touched=True,geojson_out=True, nodata=-200)
                print("  - creating additional required fields...")
                urban_pop = gpd.GeoDataFrame.from_features(result)
                urban_pop.rename(columns={'sum':'urban_pop_est'},inplace=True)
                urban_pop['area_sqkm'] = urban_pop['geometry'].area/10**6
                urban_pop['pop_per_sqkm'] = urban_pop['urban_pop_est'] / urban_pop['area_sqkm']
                # Create WKT geometry (postgis won't read shapely geometry)
                urban_pop["geometry"] = [MultiPolygon([feature]) if type(feature) == Polygon else feature for feature in urban_pop["geometry"]]
                urban_pop['geom'] = urban_pop['geometry'].apply(lambda x: WKTElement(x.wkt, srid=srid))
                urban_pop.drop('geometry', 1, inplace=True)
                # urban_pop.drop('sum', 1, inplace=True)
                # Ensure all geometries are multipolygons (specifically - can't be mixed type; complicates things)
                print(f"  - copying to postgis ({pop_feature})...")
                # Copy to project Postgis database
                urban_pop.to_sql(pop_feature, engine, if_exists='replace', index=True, dtype={'geom': Geometry('MULTIPOLYGON', srid=srid)})
            else:
                print(f"    - hex grid with population zonal statistics has already been procesed ({pop_feature}).")
    else:
        print(locale)
        xls = pandas.ExcelFile(os.path.join(cwd,'_project_configuration.xlsx'))
        df_local = pandas.read_excel(xls, 'region_settings',index_col=0)
        df_local[locale] = df_local[locale].fillna('')
        for var in [x for x in  df_local.index.values]:
            globals()[var] = df_local.loc[var][locale]
        study_region = '{}_{}_{}'.format(locale,region,year).lower()
        vic_region_sql = f'''
        SELECT "Study region" study_region, 
               geom
        FROM {study_region}
        '''
        # region specific output locations
        locale_dir = os.path.join(folder_path,'study_region','{}'.format(study_region))
        buffered_study_region = '{}_{}{}'.format(study_region,study_buffer,units)
        engine = create_engine(f"postgresql://{db_user}:{db_pwd}@{db_host}/{db}")
        clipping_boundary = gpd.GeoDataFrame.from_postgis('''SELECT geom FROM {table}'''.format(table = buffered_study_region), engine, geom_col='geom' )   
        for p in projections:
            # construct virtual raster table
            vrt = os.path.join(population_folder,f'ghs_{p}.vrt')
            population_raster_clipped   = os.path.join(locale_dir,f'ghs_{ghs_year}_{p}_{locale}.tif')
            population_raster_projected = os.path.join(locale_dir,f'ghs_{ghs_year}_{p}_{locale}_{srid}.tif')
            pop_feature = f'pop_ghs_{ghs_year}'
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
                clipping = clipping_boundary.to_crs({'init':'epsg:{}'.format(projections[p])})
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
                              new_crs = 'EPSG:{}'.format(srid))   
                print(f"  has now been created ({population_raster_projected}).")
            else:
                print(f"  has already been created ({population_raster_projected}).")
            print("Interpolation of population data to urban area...")
            analysis_area = gpd.GeoDataFrame.from_postgis(vic_region_sql,
                                                            engine, 
                                                            geom_col='geom')
            print("  - processing population zonal statistics...")
            pop_feature = "urban_study_region_pop"
            if not engine.has_table(pop_feature):
                result = zonal_stats(analysis_area,population_raster_projected,stats="sum", all_touched=True,geojson_out=True, nodata=-200)
                print("  - creating additional required fields...")
                urban_pop = gpd.GeoDataFrame.from_features(result)
                urban_pop.rename(columns={'sum':'urban_pop_est'},inplace=True)
                urban_pop['area_sqkm'] = urban_pop['geometry'].area/10**6
                urban_pop['pop_per_sqkm'] = urban_pop['urban_pop_est'] / urban_pop['area_sqkm']
                # Create WKT geometry (postgis won't read shapely geometry)
                urban_pop["geometry"] = [MultiPolygon([feature]) if type(feature) == Polygon else feature for feature in urban_pop["geometry"]]
                urban_pop['geom'] = urban_pop['geometry'].apply(lambda x: WKTElement(x.wkt, srid=srid))
                urban_pop.drop('geometry', 1, inplace=True)
                # urban_pop.drop('sum', 1, inplace=True)
                # Ensure all geometries are multipolygons (specifically - can't be mixed type; complicates things)
                print(f"  - copying to postgis ({pop_feature})...")
                # Copy to project Postgis database
                urban_pop.to_sql(pop_feature, engine, if_exists='replace', index=True, dtype={'geom': Geometry('MULTIPOLYGON', srid=srid)})
            else:
                print(f"    - hex grid with population zonal statistics has already been procesed ({pop_feature}).")
    
    # grant access to the tables just created
    engine.execute(grant_query)                                                                  
    df = pandas.read_sql(count_sql, con=engine, index_col=None)
    df.to_csv(f'./../data/study_region/{study_region}/osm_audit_{locale}_{date_yyyymmdd}.csv')
    
    
    # output to completion log					
    script_running_log(script, task, start, locale)
    engine.dispose()

if __name__ == '__main__':
    main()