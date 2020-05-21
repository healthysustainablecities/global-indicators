
#import modules
import osmnx as ox
import networkx as nx
import geopandas as gpd
import pandas as pd
import pandana as pdna
import numpy as np
from scipy.stats import zscore
import gc
import os
import csv
import matplotlib.pyplot as plt
%matplotlib inline
from shapely.geometry import Polygon, mapping

graphml_path = "belfast_gb_2019_10000m_all_osm_20190902.graphml"
G = ox.load_graphml(graphml_path)
G_undirected = ox.save_load.get_undirected(G)
gdf_osm = ox.save_load.graph_to_gdfs(G_undirected, nodes=False, edges=True)

#Impport study area
osm_buffer_file="belfast_gb_2019_1600m_buffer.gpkg"
gdf_study_area = gpd.read_file(osm_buffer_file, layer='urban_study_region')

#Import official shape file of network
gdf_official = gpd.GeoDataFrame.from_file("Belfast_City_Council_Area_Street_Network.shp")

#Convert crs of osm dataset and study area to crs to official dataset
gdf_osm = gdf_osm.to_crs(gdf_official.crs)
gdf_study_area = gdf_study_area.to_crs(gdf_official.crs)

#Plot the datasets
fig, (ax1,ax2, ax3) = plt.subplots(3, 1, figsize=( 10, 10))
gdf_osm.plot(ax=ax1)
gdf_study_area.plot(ax=ax2)
gdf_official.plot(ax=ax3)
ax1.set_title("roads")
ax2.set_title("study area")
ax3.set_title("official edges")
ax1.set_axis_off()
ax2.set_axis_off()
ax3.set_axis_off()
plt.axis('equal')
plt.show()

#Clip datasets by study are boundary
#mask1 = gdf_osm['geometry'].intersects(gdf_study_area['geometry'].unary_union)
osm_data = gpd.clip(gdf_osm, gdf_study_area)
#mask2 = gdf_official['geometry'].intersects(gdf_study_area['geometry'].unary_union)
official_data = gpd.clip(gdf_official, gdf_study_area)

#Plot the clipped dataset
fig, (ax1,ax2, ax3) = plt.subplots(3, 1, figsize=( 10, 10))
osm_data.plot(ax=ax1)
gdf_study_area.plot(ax=ax2)
official_data.plot(ax=ax3)
ax1.set_title("roads")
ax2.set_title("study area")
ax3.set_title("official edges")
ax1.set_axis_off()
ax2.set_axis_off()
ax3.set_axis_off()
plt.axis('equal')
plt.show()



# Export the clipped datasets to shapefile
from os.path import join as pjoin
filename = "belfast_official.shp"
path_to_file = pjoin("output", filename)

if os.path.isfile(path_to_file):
    print ("File exist")
else:
    official_data.to_file(path_to_file)

filename = "belfast_osm.shp"
path_to_file = pjoin("output", filename)
#gdf_osm = pd.merge(gdf_osm, gdf_osm.bounds, left_index=True, right_index=True)


if os.path.isfile(path_to_file):
    print ("File exist")
else:
    osm_data[['length', 'geometry']].to_file(path_to_file)

filename = "belfast_study_area.shp"
path_to_file = pjoin("output", filename)
#gdf_study_area = pd.merge(gdf_study_area, gdf_study_area.bounds, left_index=True, right_index=True)

if os.path.isfile(path_to_file):
    print ("File exist")
else:
    gdf_study_area.to_file(path_to_file)


#Calculating the total length of osm network
totallength = 0
count_osm = 0
osmlength = osm_data.length
for i in osmlength:
    count_osm += 1
    totallength += i
print(totallength, count_osm)


#Calculate total length of official network
totallength2 = 0
count_of = 0
oflength = official_data.length
for i in oflength:
    count_of += 1
    totallength2 += i
print(totallength2, count_of)

#calculate areal intersection with various buffering
buff = 5
percent_list = []
percent_dict = {}

while buff<20:


    official_buffer = official_data
    official_buffer = official_buffer.buffer(buff)

    osm_buffer = osm_data
    osm_buffer = osm_buffer.buffer(buff)


    osm_total = 0
    osm_areas = osm_buffer.area
    for i in osm_areas:
        osm_total += i
   # print(osm_areas[0:3])

    official_total = 0
    official_areas = official_buffer.area
    for i in official_areas:
        official_total += i
    #print(official_areas[0:3])
    print("osm areas: ", osm_total)
    print("official areas: ", official_total)

    intersected = gpd.clip(official_buffer, osm_buffer)

    totalshare = 0
    in_areas = intersected.area
    for i in in_areas:
        totalshare += i
    print(totalshare)
    percent_official_intersected = totalshare*100/official_total
    print("intersected: ",totalshare)
    print("intersected length: ", len(intersected))
    print("percent_official_intersected: ", percent_official_intersected)
    percent_dict[buff] = percent_official_intersected
    percent_list.append((buff,percent_official_intersected))

for item in percent_list:
    print("buffer: ", item[0])
    print("Percent area intersected: ", item[1])
    print("-----------------------")
