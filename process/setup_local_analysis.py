################################################################################
# Script:  setup_local_analysis.py
# Purpose: Set up study region local neighborhood analysis
# Author:  Shirley Liu
# Date:    201908
# Description: this script contains basic functions to set up sample points and sausage buffer for local neighborhood analysis

################################################################################

import networkx as nx
import time 
import osmnx as ox
import matplotlib.pyplot as plt
import numpy as np
import requests
import pandas as pd
import geopandas as gpd
import fiona

import pandana #pandana on python 3.6
from pandana.loaders import osm

import warnings
warnings.filterwarnings('ignore')



from setup_OSMnetwork import *

from descartes import PolygonPatch
from shapely.geometry import shape,Point, LineString, Polygon
from config import *


import warnings
warnings.filterwarnings('ignore')

ox.config(use_cache=True, log_console=True)

################################################################################


def get_studyregion_urban_network(network_gdf, builtup_gdf, to_crs):
    """
    Get study region OSM street network within GHS defined built-up/urban area
    
    Parameters
    ----------
    network_gdf : geodataframe
        OSM street network geodataframe
    builtup_gdf : geodataframe
        study region built-up area geodataframe
    to_crs : dict
        projected crs

    Returns
    -------
    geodataframe in UTM projection
    """
    # define projection
    builtup_gdf = builtup_gdf.to_crs(to_crs)
    network_gdf = network_gdf.to_crs(to_crs)
    # spatial join to limit street network within urban areas
    urban_edges_gdf = gpd.sjoin(network_gdf, builtup_gdf, op='intersects')
    #project to UTM for meter measure
    urban_edges_gdf_proj = ox.project_gdf(urban_edges_gdf) 
    return urban_edges_gdf_proj
################################################################################



# function to create sample point
def create_sample_points_gdf(gdf, point_dist):
    """
    Create sample point of defined point interval distance in study region street netowrk 
    
    Parameters
    ----------
    gdf : geodataframe
        OSM street network geodataframe
    point_dist : int
        sample point interval distance

    Returns
    -------
    geodataframe
    """
    #get sample point
    gdf['points'] = gdf.apply(lambda x: ox.redistribute_vertices(x.geometry, point_dist), axis=1)
    # develop edges data for each created points
    point_df = gdf['points'].apply([pd.Series]).stack().reset_index(level=1, drop=True).join(gdf).reset_index()
    point_gdf = gpd.GeoDataFrame(point_df, geometry=point_df.Series)
    return point_gdf

################################################################################


# create sausage buffer local neighborhood graph
def create_sausage_buffer_G(G_proj, orig_point, buffer=buffer_local, length=distance, intersection_tolerance = 15):
    """
    Create sausage buffer graphml for a sample point
    
    Parameters
    ----------
    G_proj : graphml
        OSM street network graphml
    orig_point : int
        the current node to start from
    buffer : float
        distance to buffer 

    length : float
        distance to search 

    intersection_tolerance: float
        nodes within this distance (in graph’s geometry’s units) will be dissolved into a single intersection

    Returns
    -------
    List [subgraph, polygon]
    """

    # locate closest node on network to 
    orig_node = ox.get_nearest_node(G_proj, orig_point, return_dist=True)
    subgraph_proj = nx.ego_graph(G_proj, orig_node[0], radius=length, distance='length')
    # create buffer
    subgraph_gdf = ox.graph_to_gdfs(subgraph_proj, nodes=False, edges=True, fill_edge_geometry=True)
    # if the subgraph is not empty, then create  buffer polygon
    if len(subgraph_gdf) > 0:
        buffer = subgraph_gdf.geometry.buffer(buffer)
        buffer_uu = buffer.geometry.unary_union 
    #if the subgraph is empty without geometry, create empty polygon as a placeholder
    else:
        buffer_uu = Polygon()

    return([subgraph_proj, buffer_uu]) #output is a list of sample point graphs, and buffer polygons




# create sausage buffer local neighborhood geodataframe
def create_sausage_buffer_gdf(G_proj, orig_point, buffer=buffer_local, length=distance, intersection_tolerance = 15):
    """
    Create sausage buffer geodataframe for a sample point
    
    Parameters
    ----------
    G_proj : graphml
        OSM street network graphml
    orig_point : int
        the current node to start from
    buffer : float
        distance to buffer 

    length : float
        distance to search 

    intersection_tolerance: float
        nodes within this distance (in graph’s geometry’s units) will be dissolved into a single intersection

    Returns
    -------
    subgraph geodataframe
    """

    # locate closest node on network to 
    orig_node = ox.get_nearest_node(G_proj, orig_point, return_dist=True)
    subgraph_proj = nx.ego_graph(G_proj, orig_node[0], radius=length, distance='length')
    subgraph_gdf = ox.graph_to_gdfs(subgraph_proj, nodes=False, edges=True, fill_edge_geometry=True)
    # create buffer polygon geometry to dataframe
    if len(subgraph_gdf) > 0:
        subgraph_gdf['geometry'] = subgraph_gdf.geometry.buffer(buffer) 
        #link original node id reference
        subgraph_gdf['node_id'] = orig_node[0]
    else:
        subgraph_gdf['geometry'] = 0
        subgraph_gdf['node_id'] = 0
    return(subgraph_gdf) #output is smaple point subgraph with buffer polygon geometry and original node id reference

################################################################################


# Local neighbourhood analysis
def analyse_local_nh(G_proj, orig_point, buffer=buffer_local, length=distance, intersection_tolerance = 15):
    """
    Get sausage buffer and sample point stats/variables
    
    Parameters
    ----------
    G_proj : graphml
        OSM street network graphml
    orig_point : int
        the current node to start from

    Returns
    -------
    dict
    """

    buffer = create_sausage_buffer_G(G_proj, orig_point)
    orig_node = ox.get_nearest_node(G_proj, orig_point, return_dist=True)
    #get stats
    area_sqm = buffer[1].area
    area_sqkm = area_sqm*1e-06
    
    # count number of intersection if it is euqal to zero
    node_ids = set(buffer[0].nodes())
    intersection_count = len([True for node, count in buffer[0].graph['streets_per_node'].items() if (count > 1) and (node in node_ids)])
    
    if intersection_count > 0:
        stats = ox.basic_stats(buffer[0], area=area_sqm, clean_intersects=True, circuity_dist='euclidean')
    elif area_sqm > 0: 
        stats = ox.basic_stats(buffer[0], area=area_sqm, clean_intersects=False, circuity_dist='euclidean')
    else:
        stats = {'n': 0,
                 'm': 0,
                 'k_avg': 0,
                 'intersection_count': 0,
                 'streets_per_node_avg': 0,
                 'streets_per_node_counts': 0,
                 'streets_per_node_proportion': 0,
                 'edge_length_total': 0,
                 'edge_length_avg': 0,
                 'street_length_total': 0,
                 'street_length_avg': 0,
                 'street_segments_count': 0,
                 'node_density_km': 0,
                 'intersection_density_km': 0,
                 'edge_density_km': 0,
                 'street_density_km': 0,
                 'circuity_avg': 0,
                 'self_loop_proportion': 0,
                 'clean_intersection_count': 0,
                 'clean_intersection_density_km': 0}       
    return({ 'origin_node_id': orig_node[0],
             'area_sqkm': area_sqkm,
             'stats': stats,
             'origin_node_snap_dist': orig_node[1]})
################################################################################



# accessibility analysis - pandana accessibility

# configure search at a max distance for up to the first nearest points-of-interest
num_pois = 1
num_categories = len(shop) + 1 #one for each amenity, plus one extra for all of them combined


def get_pandana_network(G_filename, folder, bbox=None):
    """
    get OSM network with study region bounding box using Pandana
    
    Parameters
    ----------
    G_filename : string
        OSM street network graphml filename
    folder : string
        folder to OSM street network file
    bbox : list
        study region bounding box geometry
        

    Returns
    -------
    pandana network
    """

    start_time = time.time()
    if os.path.isfile(folder + "/" + G_filename):
        method = 'loaded from graphml'
        G_osm_walk = ox.load_graphml(G_filename, folder)
        # get gdf nodes and edges
        gdf_osm_walk_nodes = ox.graph_to_gdfs(G_osm_walk, nodes=True, edges=False)
        gdf_osm_walk_edges = ox.graph_to_gdfs(G_osm_walk, nodes=False, edges=True)
        # get network from Pandana
        network=pandana.network.Network(gdf_osm_walk_nodes["x"], gdf_osm_walk_nodes["y"], gdf_osm_walk_edges["u"], gdf_osm_walk_edges["v"],
                 gdf_osm_walk_edges[["length"]])
    
    else:
        method = 'downloaded from OSM'
        # otherwise, query the OSM API for the street network within the bounding box
        G_osm_walk = ox.graph_from_bbox(north=bbox[2], south=bbox[0], east=bbox[3], west=bbox[1], network_type= 'walk', retain_all=True, buffer_dist=1e4)
        # get gdf nodes and edges
        gdf_osm_walk_nodes = ox.graph_to_gdfs(G_osm_walk, nodes=True, edges=False)
        gdf_osm_walk_edges = ox.graph_to_gdfs(G_osm_walk, nodes=False, edges=True)
    
        # get network from Pandana
        network=pandana.network.Network(gdf_osm_walk_nodes["x"], gdf_osm_walk_nodes["y"], gdf_osm_walk_edges["u"], gdf_osm_walk_edges["v"],
                 gdf_osm_walk_edges[["length"]])
    print('Network with {:,} nodes {} in {:,.2f} secs'.format(len(network.node_ids), method, time.time()-start_time))
    return network  



def get_nearest_node_to_pois(pandana_network, pois_df, distance, num_pois):
    """
    get nearest nodes of pois within designated distance threshold
    
    Parameters
    ----------
    pandana_network : network graph
        pandana OSM street network graph
    pois_df : dataframe
        point of interest dataframe
    distance : float
        distance threshold
    num_pois : int
        number of point of interest to search


    Returns
    -------
    dataframe
    """

    # precomputes the range queries (the reachable nodes within this maximum distance)
    # so, as long as you use a smaller distance, cached results will be used
    start_time = time.time()
    pandana_network.precompute(distance + 1)
    
    # initialize a category for all amenities with the locations specified by the lon and lat columns
    pandana_network.set_pois(category='all', maxdist=distance, maxitems=num_pois, x_col=pois_df['lon'], y_col=pois_df['lat'])

    # searches for the n nearest amenities (of all types) to each node in the network
    all_access = pandana_network.nearest_pois(distance=distance, category='all', num_pois=num_pois)

    # it returned a df with the number of columns equal to the number of POIs that are requested
    # each cell represents the network distance from the node to each of the n POIs
    print('{:,} nodes in {:,.2f} secs'.format(len(all_access), time.time()-start_time))
    return all_access




def add_access_score_to_df(origin_node_df, sample_points_df, distance, col_name):
    """
    add pandana accessibility score to sampe point/local neighborhood stats dataframe
    
    Parameters
    ----------
    origin_node_df : datafram
        dataframe with nearest nodes and distance to first pois
    sample_points_df : dataframe
        sample point dataframe
    distance : float
        distance threshold
    col_name : string
        new column name for accessibility score

    Returns
    -------
    dataframe
    """
    

    # keep nodes with the nearest (first) pois within certain distance 
    nodes_pois = origin_node_df[origin_node_df[1] < distance][[1]]

    # merge sample point dataframe to get the accessibility distance
    sample_points_df.node_id = sample_points_df.node_id.astype(int)
    sample_points_df = pd.merge(left=sample_points_df, right=nodes_pois, how='left', left_on='node_id', right_index=True)
    sample_points_df = sample_points_df.rename(columns={1:col_name})
    
    #fill none value as 0 indicating that the nearest shop is not within 1km of the nodes/sample point
    #fill values morethan 0 as 1 indicating that the nearest shop is within 1km of the nodes/sample point
    sample_points_df[col_name] = sample_points_df[col_name].fillna(0) 
    sample_points_df.loc[sample_points_df[col_name] > 0, col_name] = 1
    
    return sample_points_df


################################################################################

# accessibility analysis - sausage buffer accessibility
def get_nodeid_pois_sausagebuffer_intersection(sausagebuffer_gdf, pois_gdf):
    
    """
    get nearest nodes of pois within sausage buffer intersection
    
    Parameters
    ----------
    sausagebuffer_gdf : geodataframe
        sausage buffer geodataframe
    pois_gdf : dataframe
        point of interest geodataframe

    Returns
    -------
    dataframe
    """

    # make sure sausagebuffer and pois_gdf is in the same projection system
    # create an empty list
    buffer_node_id = pd.DataFrame()
    # loop through sausage buffer intersection with pois
    for x in range(0, len(sausagebuffer_gdf)):
        buffer_node_id1 = pd.DataFrame()
        #Returns a Series of dtype('bool') with value True for each polygon geometry that intersects other.
        pois_intersect = sausagebuffer_gdf[x].geometry.intersects(pois_gdf['geometry'].unary_union) 
        # return a dataframe with pois within local walkable neighborhood (pois intersecting buffer), 
        # retain orignal node id for reference in sample point neighborhood
        buffer_node_id1['pois_walkable_node_id'] = [sausagebuffer_gdf[x][pois_intersect]['node_id'].max()]
        buffer_node_id = buffer_node_id.append(buffer_node_id1, ignore_index=True).dropna().astype(int)
        intersection_node_id = buffer_node_id.drop_duplicates('pois_walkable_node_id')
    return intersection_node_id





