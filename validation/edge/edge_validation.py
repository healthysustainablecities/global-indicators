
import json
import os

import geopandas as gpd
import matplotlib.pyplot as plt

import osmnx as ox


# For 'filename', insert belfast.json, hong_kong.json, or olomouc.json
def load_data(filename, city):
    # Get the work directory
    dirname = os.path.abspath('')
    # Define the path for the city-specifc configuration file
    jsonFile = 'configuration/' + filename
    jsonPath = os.path.join(dirname, jsonFile)
    # Use the defined paths to run the config file
    try:
        with open(jsonPath) as json_file:
            config = json.load(json_file)
    except Exception as e:
        print('Failed to read json file.')
        print(e)

    # Read the filepaths so data can be accessed
    graphml_path = os.path.join(dirname, 'data', city, config['graphml_path'])
    osm_buffer_path = os.path.join(dirname, 'data', city, config['osm_buffer'])
    gdf_official_path = os.path.join(dirname, 'data', city, config ['gdf_official'])

    return (graphml_path, osm_buffer_path, gdf_official_path)

def refine_data(graphml_path, osm_buffer_path, gdf_official_path):
    # Extract specific layers from the data
    G = ox.load_graphml(graphml_path)
    G_undirected = ox.get_undirected(G)
    gdf_osm = ox.utils_graph.graph_to_gdfs(G_undirected, nodes=False, edges=True)
    gdf_study_area = gpd.read_file(osm_buffer_path, layer='urban_study_region')
    # Project the data to a common crs
    gdf_osm = gdf_osm.to_crs(gdf_official_path.crs)
    gdf_study_area = gdf_study_area.to_crs(gdf_official_path.crs)

    return (gdf_osm, gdf_study_area)

def clip_data(gdf_osm, gdf_official, gdf_study_area):
    # Convert crs of OSM data and Study Area to the crs of the official data
    #gdf_osm = ox.project_graph(gdf_osm, to_crs=to_crs)
    #gdf_study_area = ox.project_graph(gdf_study_area, to_crs=config['to_crs)'])

    #gdf_osm = gdf_osm.to_crs(gdf_official.crs)
    #gdf_study_area = gdf_study_area.to_crs(gdf_official.crs)

    # Clip datasets by study are boundary
    osm_data_clipped = gpd.clip(gdf_osm, gdf_study_area)
    official_clipped = gpd.clip(gdf_official_path, gdf_study_area)

    return (osm_data_clipped, official_clipped)

# Plot the datasets
def plot_map(x):
    fig, ax = plt.subplots(figsize=(10, 10))
    ax = x.plot(ax=ax)
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
