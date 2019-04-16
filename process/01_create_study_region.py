# Script:  01_study_region_setup.py
# Purpose: Python set up study region boundaries
# Author:  Carl Higgs
# Date:    2018 06 05

import time
import geopandas as gpd
from geoalchemy2 import Geometry, WKTElement
from sqlalchemy import create_engine
import folium

from script_running_log import script_running_log

# Import custom variables for National Liveability indicator process
from _project_setup import *

# simple timer for log file
start = time.time()
script = os.path.basename(sys.argv[0])
task = 'create study region boundary files in new geodatabase'

engine = create_engine("postgresql://{user}:{pwd}@{host}/{db}".format(user = db_user,
                                                                      pwd  = db_pwd,
                                                                      host = db_host,
                                                                      db   = db))

print("Import administrative boundaries for study region... "),
for area in areas:
  if areas[area]['data'].endswith('zip'):
    # Open zipped file as geodataframe
    gdf = gpd.read_file('zip://{}'.format(areas[area]['data']))
  else:
    # Open spatial file as geodataframe
    gdf = gpd.read_file(areas[area]['data'])
  # Restrict to relevant region based on filter value 
  # (this assumes filter value and field is common to 
  gdf = gdf[gdf[area_filter_field]==area_filter_value]
  
  # Set index
  gdf.set_index(areas[area]['id'],inplace=True)
  # Transform to project projection
  gdf.to_crs(epsg=srid, inplace=True)
  # Create WKT geometry (postgis won't read shapely geometry)
  gdf['geom'] = gdf['geometry'].apply(lambda x: WKTElement(x.wkt, srid=srid))
  # Drop original shapely geometry
  gdf.drop('geometry', 1, inplace=True)
  # Copy to project Postgis database
  gdf.to_sql(areas[area]['name_s'], engine, if_exists='replace', index=True, dtype={'geom': Geometry('POLYGON', srid=srid)})
  print('\t{} {} imported'.format(len(gdf),areas[area]['name_f'])), 

print("\nCreate analytical boundaries...")
print("\tCreate study region boundary... ")
engine.execute('''
DROP TABLE IF EXISTS {study_region}; 
CREATE TABLE {study_region} AS 
      SELECT '{study_region}'::text AS description,
             geom 
        FROM {region_shape} 
       WHERE {where};
'''.format(study_region = study_region,
           region_shape = region_shape,
           where = region_where_clause))

print("\tCreate {} km buffered study region... ".format(study_buffer))
engine.execute('''
DROP TABLE IF EXISTS {buffered_study_region}; 
CREATE TABLE {buffered_study_region} AS 
      SELECT '{study_region} with {buffer} m buffer'::text AS description, 
             ST_Buffer(geom,{buffer}) AS geom 
        FROM {study_region};
'''.format(study_region = study_region,
           buffered_study_region = buffered_study_region,
           buffer = study_buffer))

# Prepare map
map_layers={}
map_layers['study_region'] = gpd.GeoDataFrame.from_postgis('''SELECT 'Bangkok' AS "Description",ST_Transform(geom,4326) geom FROM {}'''.format(study_region), engine, geom_col='geom' )
map_layers['buffer'] = gpd.GeoDataFrame.from_postgis('''SELECT '10km study region buffer' AS "Description",ST_Transform(geom,4326) geom FROM {}'''.format(buffered_study_region), engine, geom_col='geom' )
map_layers[areas[0]['name_s']] = gpd.GeoDataFrame.from_postgis('''SELECT "{id}" As "Subdistrict",ST_Transform(geom,4326) geom FROM {table}'''.format(id = areas[0]['id'],table = areas[0]['name_s']), engine, geom_col='geom' )
# get map centroid from study region
xy = [float(map_layers['study_region'].centroid.y),float(map_layers['study_region'].centroid.x)]    

# initialise map
m = folium.Map(location=xy, zoom_start=10, control_scale=True, prefer_canvas=True)
m.add_tile_layer(tiles='Stamen Toner',name='simple map', overlay=True,active=True)
# add layers (not true choropleth - for this it is just a convenient way to colour polygons)
buffer = folium.Choropleth(map_layers['buffer'].to_json(),name='10km study region buffer',fill_color=colours['qualitative'][1],fill_opacity=0,line_color=colours['qualitative'][1], highlight=True).add_to(m)
folium.features.GeoJsonTooltip(fields=['Description'],
                               labels=True, 
                               sticky=True
                              ).add_to(buffer.geojson)


study_region = folium.Choropleth(map_layers['study_region'].to_json(),name='Study region',fill_color=colours['qualitative'][0],line_color=colours['qualitative'][0], highlight=True).add_to(m)
folium.features.GeoJsonTooltip(fields=['Description'],
                               labels=True, 
                               sticky=True
                              ).add_to(study_region.geojson)

feature = folium.Choropleth(map_layers[areas[0]['name_s']].to_json(),name=str.title(areas[0]['name_f']), highlight=True).add_to(m)
folium.features.GeoJsonTooltip(fields=['Subdistrict'],
                               labels=True, 
                               sticky=True
                              ).add_to(feature.geojson)

folium.LayerControl(collapsed=False).add_to(m)

# checkout https://nbviewer.jupyter.org/gist/jtbaker/57a37a14b90feeab7c67a687c398142c?flush_cache=true
# save map
map_name = '01_study_region.html'
m.save('../maps/{}'.format(map_name))
print("\nPlease inspect results using interactive map saved in project maps folder: {}\n".format(map_name))
# output to completion log					
script_running_log(script, task, start, locale)
engine.dispose()
