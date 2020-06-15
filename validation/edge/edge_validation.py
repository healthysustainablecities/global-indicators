
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
from shapely.geometry import Polygon, mapping
import json
import sys
from os.path import join as pjoin


def load_data(name):
    if name == '__main__':
        # use the script from command line, change directory to '/validation/edge' folder
        # then 'python edge_validation.py belfast.json' to process city-specific indicators
        startTime = time.time()

        # get the work directory
        dirname = os.path.abspath('')

        # the configuration file should put in the '/configuration' folder located at the same folder as scripts
        # load city-specific configeration file
        jsonFile = 'configuration/' + sys.argv[1]
        jsonPath = os.path.join(dirname, jsonFile)
        try:
            with open(jsonPath) as json_file:
                config = json.load(json_file)
        except Exception as e:
            print('Failed to read json file.')
            print(e)

        # output the processing city name to users
        print('Process city: {}'.format(config['study_region']))

        # read graphml filepath and create layer
        graphml_path = os.path.join(dirname, config['folder'],
                                            config['graphml_path'])
        G = ox.load_graphml(graphml_path)
        G_undirected = ox.save_load.get_undirected(G)
        gdf_osm = ox.save_load.graph_to_gdfs(G_undirected, nodes=False, edges=True)

        # read OSM_Buffer filepath and create a gdf for study area
        osm_buffer = os.path.join(dirname, config['folder'],
                                            config['osm_buffer_file'])
        gdf_study_area = gpd.read_file(osm_buffer, layer='urban_study_region')

        # read official shape file of network filepath
        gdf_official = os.path.join(dirname, config['folder'],
                                            config['gdf_official'])

        # Convert crs of osm dataset and study area to crs to official dataset
        gdf_osm = gdf_osm.to_crs(gdf_official.crs)
        gdf_study_area = gdf_study_area.to_crs(gdf_official.crs)

        # Clip datasets by study are boundary
        osm_data_clipped = gpd.clip(gdf_osm, gdf_study_area)
        gdf_study_area_clipped = gpd.clip(gdf_official, gdf_study_area)

        return (gdf_osm, gdf_official, gdf_study_area, 
            osm_data_clipped, official_clipped)   

# Plot the datasets
def plot_map(x):
    fig, ax1 = plt.subplots(figsize=(10, 10))
    x.plot(ax=ax)
    ax.set_axis_off()
    plt.axis('equal')
    plt.show()


# Calculate the total length of network
# Dataname can be either 'gdf_osm' or 'gdf_official'
def total_length(dataname):
    totallength = 0
    count = 0
    length = dataname.length
    for i in length:
        count += 1
        totallength += i
    print(totallength + "; " + count)

# Calculate area intersection with various buffering
# Dataname can be either 'official_buffer' or 'osm_buffer'
def buffer_intersected(x, dataname):
    buff = x
    while buff<20:
        official_buffer = official_data.buffer(buff)
        osm_buffer = osm_data.buffer(buff) 
        total = 0
        area = dataname.area
        for i in area:
            total += i
        print(dataname + ": " + total)

# Calculate shared area of intersection with various buffering
def shared_area(x):
    buff = x
    percent_list = []
    percent_dict = {}
    while buff<20:
        official_buffer = official_data.buffer(buff)
        osm_buffer = osm_data.buffer(buff) 
        intersected = gpd.clip(official_buffer, osm_buffer)
        totalshare = 0
        in_areas = intersected.area
        for i in in_areas:
            totalshare += i
        print('Share of Buffered Area:' + totalshare)
            
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
