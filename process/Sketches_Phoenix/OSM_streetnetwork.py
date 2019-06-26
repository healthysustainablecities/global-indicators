# Script:  OSM_streetnetwork.py
# Purpose: Create street networks for specified city
# Author:  Shirley Liu
# Date:    201905
# Description: this script contains the to generate study region boundaries and street network using OSMnx, the output produced through this process will be stored in data folder

# Libraries used for OSMnx analyses and output
import networkx as nx
import time 
import osmnx as ox
import matplotlib.pyplot as plt
import numpy as np
import requests
import fiona
import pandas as pd
import config

ox.config(use_cache=True, log_console=True)
ox.__version__




# retain study region shape and save as shapefile
def studyregion(address):
    G = ox.gdf_from_place(address)
    ox.save_gdf_shapefile(G, filename='{studyregion}_shape{suffix}.graphml'.format(studyregion = address,
                                                                                   suffix = config.time), folder = config.OSM_data_loc)
    return G



# retain 10km buffered study region shape and save as shapefile
def studyregion_buffered(address):
    G = ox.gdf_from_place(address, buffer_dist=1e4)
    ox.save_gdf_shapefile(G, filename='{studyregion}_buffered{suffix}.graphml'.format(studyregion = address,
                                                                                   suffix = config.time), folder = config.OSM_data_loc)
    return G




# Extract complete OSM network: "all (non-private) OSM streets and paths"

def OSM_all(address):    
    W_all = ox.graph_from_place(address, network_type= 'all', retain_all = True, buffer_dist=1e4)
    ox.save_graphml(W_all, filename='{studyregion}_all{suffix}.graphml'.format(studyregion = address,
                                                                                   suffix = config.time), folder = config.OSM_data_loc)
    W_all_proj = ox.project_graph(W_all)
    W_proj_gdfs = ox.graph_to_gdfs(W_all_proj, nodes=False, edges=True, fill_edge_geometry=True)
    
    #show network figure
    fig, ax = plt.subplots(figsize=(10, 10))
    ax = W_proj_gdfs.plot(ax=ax)
    ax.set_title(address)
    ax.set_axis_off()
    fig.suptitle('All OSM street network', fontsize=14, fontweight='bold')
    fig.text(0.1, 0, 'Note: all non-private street network')
    plt.show()




# Extract pedestrain OSM network
def OSM_walk(address):
    W_walk = ox.graph_from_place(address, network_type= 'walk', retain_all=True, buffer_dist=1e4)
    ox.save_graphml(W_walk, filename='{studyregion}_walk{suffix}.graphml'.format(studyregion = address,
                                                                                   suffix = config.time), folder = config.OSM_data_loc)
    
    W_walk_proj = ox.project_graph(W_walk)
    W_proj_gdfs = ox.graph_to_gdfs(W_walk_proj, nodes=False, edges=True, fill_edge_geometry=True)
    
    #show network figure
    fig, ax = plt.subplots(figsize=(10, 10))
    ax = W_proj_gdfs.plot(ax=ax)
    ax.set_title(address)
    ax.set_axis_off()
    fig.suptitle('All OSM pedestrain network', fontsize=14, fontweight='bold')
    fig.text(0.1, 0, 'Note: based on OSMnx walk network type')
    plt.show()

    

    
# Extract cycle OSM network
def OSM_bike(address):
    W_walk = ox.graph_from_place(address, network_type= 'bike', retain_all=True, buffer_dist=1e4)
    ox.save_graphml(W_walk, filename='{studyregion}_bike{suffix}.graphml'.format(studyregion = address,
                                                                                   suffix = config.time), folder = config.OSM_data_loc)
    
    W_walk_proj = ox.project_graph(W_walk)
    W_proj_gdfs = ox.graph_to_gdfs(W_walk_proj, nodes=False, edges=True, fill_edge_geometry=True)
    
    #show network figure
    fig, ax = plt.subplots(figsize=(10, 10))
    ax = W_proj_gdfs.plot(ax=ax)
    ax.set_title(address)
    ax.set_axis_off()
    fig.suptitle('All OSM pedestrain network', fontsize=14, fontweight='bold')
    fig.text(0.1, 0, 'Note: based on OSMnx bike network type')
    plt.show()
    


    
# Obtain Basic OSM network stats (all non-private street, walk network type, bike network type)
def OSM_basicstats(address):
    df = pd.DataFrame()
    for networktype in ['all', 'walk', 'bike']:
        w = ox.graph_from_place(address, network_type=networktype, retain_all=True, buffer_dist=1e4)
        w_proj = ox.project_graph(w)
    
        nodes_proj = ox.graph_to_gdfs(w_proj, edges=False)
        graph_area_m = nodes_proj.unary_union.convex_hull.area
    
        stats = ox.basic_stats(w_proj, area=graph_area_m, clean_intersects=True, circuity_dist='euclidean', tolerance=15)
        df1 = pd.DataFrame.from_dict(stats, orient='index', columns=[networktype + address])
        df = pd.concat([df, df1], axis=1)
    return df





# Retain clean intersection graph with different tolerance levels
def OSM_clean_intersection(address):
    G = ox.graph_from_address(address, network_type= 'walk', distance=750)
    G_proj = ox.project_graph(G)
    G_proj_gdfs = ox.graph_to_gdfs(G_proj, nodes=False, edges=True, fill_edge_geometry=True)
    #itereate over cleaning buffer distance
    buffers = [15,12,10,8,5]
    # instantiate plot
    fig, axarr = plt.subplots(ncols=5, sharex='col', sharey='row', squeeze=False, figsize=(25,10))
    for i in range(len(buffers)):
        # clean up the intersections and extract their xy coords
        intersections = ox.clean_intersections(G_proj, tolerance=buffers[i], dead_ends=False)
        points = np.array([point.xy for point in intersections])
        # plot the cleaned-up intersections
        G_proj_gdfs.plot(ax = axarr[0][i])
        axarr[0][i].scatter(x=points[:,0], y=points[:,1], s = 10, zorder=2, color=None, edgecolors='#000000')
        axarr[0][i].set_title("Tolerance: {}".format(buffers[i]))
        axarr[0][i].set_aspect(1)
        axarr[0][i].set_axis_off()
        # axarr[0][i].add_patch(patches.Rectangle((0.8, 0.8), 0.2, 0.2))
    plt.suptitle(address, fontsize=14, fontweight='bold')    
    plt.tight_layout()
    plt.show()
    return intersections

