import os
import pandas
import requests
import sys
import time
import subprocess as sp
from datetime import datetime
from pandas.io.json import json_normalize
import geopandas as gpd
import osmnx as ox

url = 'http://overpass-api.de/api/interpreter'

# Load settings from _project_configuration.xlsx
# xls = pandas.ExcelFile(os.path.join(sys.path[0],'D:/ind_bangkok/process/osm_audit_template.xlsx'))
xls = pandas.ExcelFile(os.path.join(sys.path[0],'osm_audit_template.xlsx'))
df = pandas.read_excel(xls, 'audit_template')
locations = pandas.read_excel(xls, 'locations',index_col='city')

cities = list(locations.index)

def get_poi_counts(bbox,key,value):
    try:
        if '{}'.format(value)=='nan':
            category = "  {}: ".format(key)
            r = requests.get(url, params={'data': '''
            [out:json];
            (
              node["{key}"]({bbox});
              way["{key}"]({bbox});
              relation["{key}"]({bbox});
            );
            out count;'''.format(key=key, bbox = bbox)}).json()['elements'][0]['tags']['total']
        else:
            cities = "  {}={}: ".format(key,value)
            r = requests.get(url, params={'data': '''
            [out:json];
            (
              node["{key}"="{value}"]({bbox});
              way["{key}"="{value}"]({bbox});
              relation["{key}"="{value}"]({bbox});
            );
            out count;
            '''.format(key=key, value=value, bbox =  bbox)}).json()['elements'][0]['tags']['total']
        print('{}{}'.format(category,r))
    except:
        r = "error"
    return r

# get bbox
locations['bbox']=''
for city in cities:
    print(city)
    format = [f.strip() for f in locations.loc[city,'city_boundary_format'].split(':')]
    if format[0]=='bbox':
        bbox = format[1].split(',')
        locations.loc[city,'bbox'] = ','.join(['{}'.format(bbox[i]) for i in [1,0,3,2]])
    elif format[0]=='gpkg':
      gpkg = locations.loc[city,'city_boundary_data']
      layer = format[1]
      gdf = gpd.read_file(gpkg,layer=layer,where=locations.loc[city,'city_boundary_query'])
      if gdf.crs == {}:
            gdf.crs = {'init':'epsg:{}'.format(locations.loc[city,'boundary_epsg'])}
      if gdf.crs!=4326:
        gdf = gdf.to_crs(epsg=4326)
      # get bounding box in Overpass API req'd format of miny, minx, maxy, maxx
      bbox = gdf.total_bounds
      locations.loc[city,'bbox'] = ','.join(['{}'.format(bbox[i]) for i in [1,0,3,2]])
    elif format[0].endswith('zip'):
      # Open zipped file as geodataframe
      gdf = gpd.read_file('zip://{}'.format(locations.loc[city,'city_boundary_data']))
      if gdf.crs == {}:
            gdf.crs = {'init':'epsg:{}'.format(locations.loc[city,'boundary_epsg'])}
      if gdf.crs!=4326:
        gdf = gdf.to_crs(epsg=4326)
      bbox = gdf.total_bounds
      locations.loc[city,'bbox'] = ','.join(['{}'.format(bbox[i]) for i in [1,0,3,2]])
    else:
      # Open spatial file as geodataframe
      gdf = gpd.read_file('{}'.format(locations.loc[city,'city_boundary_data']))
      if gdf.crs == {}:
            gdf.crs = {'init':'epsg:{}'.format(locations.loc[city,'boundary_epsg'])}
      if gdf.crs!=4326:
        gdf = gdf.to_crs(epsg=4326)
      bbox = gdf.total_bounds
      locations.loc[city,'bbox'] = ','.join(['{}'.format(bbox[i]) for i in [1,0,3,2]])
    
for city in cities:
    print(city),
    bbox = locations.loc[city,'bbox']
    print(" (bounding box: {})".format(bbox))
    if city in df.columns:
        df.loc[df[city]=='error',city] = df.loc[df[city]=='error',city].apply(lambda x: get_poi_counts(key = x.key,  
                                                                                                       value = x.value, 
                                                                                                       bbox = bbox),
                                                                              axis=1)
    else:
        df[city] = df.apply(lambda x: get_poi_counts(key = x.key, value = x.value, bbox = bbox),axis=1)

df.to_csv('osm_audit.csv')
