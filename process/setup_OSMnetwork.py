################################################################################
# Script:  setup_network.py
# Purpose: Set up study region street networks
# Author:  Shirley Liu
# Date:    201905
# Description: this script contains basic functions to set up study regions including retriving buffered study region boundaries, bounding box and street network using OSMnx

################################################################################

# Libraries used for analyses and output
import matplotlib.pyplot as plt
import pandas as pd
import geopandas as gpd
import numpy as np
import requests
import osmnx as ox
import networkx as nx
import time 
import os

from shapely.geometry import shape,Point, LineString, Polygon
from descartes import PolygonPatch

ox.config(use_cache=True, log_console=True)


# project config
import config

suffix = '_201905' # output data time
buffer_dist = 1e4 # study region buffer 10km
data_folder = '../data/Maricopa_County' # studyregion administrative data folder 
OSM_folder = '../data/OSM' # folder path to save OSM data 

################################################################################


# Define place boundary projection
def project_studyregion_gdf(filepath, to_crs=None, to_latlong=False):
    """
    Project a GeoDataFrame from file to the UTM zone appropriate for its geometries' centroid.
    
    Parameters
    ----------
    filepath : String
        the name of the shapefile path(including file extension)
    to_crs : dict
        if not None, just project to this CRS instead of to UTM
    to_latlong : bool
        if True, projects to latlong instead of to UTM
    Returns
    -------
    GeoDataFrame
    """
    gdf = gpd.GeoDataFrame.from_file(filepath)
    gdf_proj = ox.project_gdf(gdf, to_crs=to_crs, to_latlong=to_latlong)
    return gdf_proj
################################################################################


# Get place boundary with 10km buffer
def get_bufferedstudyregion_polygon(filepath, buffer_dist=1e4, crs=None, to_crs=None, to_latlong=True):
    """
    Convert a GeoDataFrame from file to shapely polygon with the UTM zone appropriate for its geometries'
    centroid.
    
    Parameters
    ----------
    filepath : String
        the name of the shapefile path(including file extension)
    buffer_dist : float 
        distance to buffer around the place geometry, in meters
    crs : dict 
        the starting coordinate reference system of the passed-in geometry, 
        default value (None) will set settings.default_crs as the CRS
    to_crs : dict
        if not None, just project to this CRS instead of to UTM
    to_latlong : bool
        if True, projects to latlong instead of to UTM
    Returns
    -------
    tuple
        (geometry_proj, crs), the projected shapely geometry and the crs of the
        projected geometry
    """
    # load shaplefile
    shape = gpd.GeoDataFrame.from_file(filepath)
    # create buffer
    polygon = shape['geometry'].iloc[0]
    buffer_polygon = polygon.buffer(buffer_dist)
    # Project a shapely Polygon from lat-long to UTM, or vice-versa 
    polygon_buffer_prof = ox.project_geometry(buffer_polygon, crs=crs, to_crs=to_crs, to_latlong=to_latlong)
    return polygon_buffer_prof

################################################################################


# get bounding box from study region boundary shapefile
# check the shapefile format, study region boundary shapefile should specify lat lon geometry
# Bounding box formatted as a 4 element tuple: (lng_max, lat_min, lng_min, lat_max)
# otherwise, we can use can generate a bounding box by going to http://boundingbox.klokantech.com/ and selecting the CSV format.
def get_bufferedstudyregion_bbox(filepath, place=None, buffer_dist=1e4, crs=None, to_crs=None, to_latlong=True):
    """
    If the studyregion shapefile exist:
    Get bbox from a GeoDataFrame file with the UTM zone appropriate for its geometries' centroid.
    Bounding box formatted as a 4 element tuple: (lng_max, lat_min, lng_min, lat_max)
    
    Else:
    Get bbox from the query to geocode to get geojson boundary polygon from OSM
    
    Parameters
    ----------
    filepath : String
        the name of the shapefile path(including file extension)
    place : String 
        the query to geocode to get geojson boundary polygon
    buffer_dist : float 
        distance to buffer around the place geometry, in meters
    crs : dict 
        the starting coordinate reference system of the passed-in geometry, 
        default value (None) will set settings.default_crs as the CRS
    to_crs : dict
        if not None, just project to this CRS instead of to UTM
    to_latlong : bool
        if True, projects to latlong instead of to UTM
    Returns
    -------
    tuple
        (geometry_proj, crs), the projected shapely geometry and the crs of the
        projected geometry
    """
    if os.path.exists(filepath):
        polygon_buffer = get_bufferedstudyregion_polygon(filepath, buffer_dist=1e4, crs=crs, to_crs=to_crs, to_latlong=True)
        bbox = polygon_buffer[0].bounds 
    else:
        gdf = ox.gdf_from_place(query, gdf_name=None, which_result=1, buffer_dist=buffer_dist)
        bbox = gdf.geometry.bounds[['miny','minx','maxy','maxx']].values[0].tolist()
        bbox = ','.join(['{}'.format(x) for x in bbox])
    return bbox
################################################################################


#Get pedestrain street network and save to local folder
# Extract complete OSM network and save local graph and edge shapefile: "all (non-private) OSM streets and paths"
def Save_OSM_G_gdf(polygon, network_type= 'walk', placename=None, suffix=suffix, folder=OSM_folder):    
    """
    save a graphml and GeoDataFrame from a single polygon.
    Parameters
    ----------
    polygon : shapely Polygon or MultiPolygon
        the shape to get network data within. coordinates should be in units of
        latitude-longitude degrees.
    network_type : string
        what type of street network to get. Default type is pedestrain network
    placename: string
        place name
    suffix: string
        output data date
    folder : string
        where to save the shapefile, specify local folder path for OSM resource
    Returns
    -------
    none

    """
    #The graph_from_polygon function requires a polygon in units of lat-long (epsg 4326)
    G = ox.graph_from_polygon(polygon, network_type=network_type, retain_all = True)
    #save network as graphml
    ox.save_graphml(G, filename='{studyregion}_{network_type}{suffix}.graphml'.format(
        studyregion = placename, network_type=network_type, suffix = suffix), folder=folder)
    
    #set up project projection, and save the projected graph for efficiency loading purpose
    G_proj = ox.project_graph(G)
    ox.save_graphml(G_proj, filename='{studyregion}_proj_{network_type}{suffix}.graphml'.format(
        studyregion = placename, network_type=network_type, suffix = suffix), folder=folder)
    
    #save projected network geodataframe as shapefile (project to UTM so we can use metres as a unit when buffering)
    edges_proj_gdfs = ox.graph_to_gdfs(G_proj, nodes=False, edges=True, fill_edge_geometry=True)
    ox.save_gdf_shapefile(edges_proj_gdfs, filename='{studyregion}_proj_{network_type}{suffix}'.format(
        studyregion = placename, network_type=network_type, suffix = suffix), folder=folder)
    
    #show network figure
    fig, ax = plt.subplots(figsize=(5, 5))
    ax = edges_proj_gdfs.plot(ax=ax)
    ax.set_title(address)
    ax.set_axis_off()
    fig.suptitle('{} OSM {} street network'.format(placename, network_type), fontsize=14, fontweight='bold')
    plt.show()
################################################################################


    
    
    
# Load pedestrain street network from local folder

def get_OSM_G(G_filename, OSM_folder, polygon=None, network_type= 'walk'):
    """
    If studyregion graphml file exist:
    Load a GraphML file from disk
    
    Else:
    Query from OSM from studyregion polygon to get the network

    Parameters
    ----------
    G_filename : string
        the name of the graphml file (including file extension)
    OSM_folder : string
        the folder containing the OSM file, if None, use default data folder
    polygon : shapely Polygon or MultiPolygon
        the shape to get network data within. coordinates should be in units of
        latitude-longitude degrees.
    network_type : string
        what type of street network to get. Default type is pedestrain network  

    Returns
    -------
    networkx multidigraph
    """
    if os.path.exists(OSM_folder +'/' + G_filename):
        G = ox.load_graphml(filename=G_filename, folder=OSM_folder)
    else:
        G = ox.graph_from_polygon(polygon, network_type=network_type, retain_all = True)
    return G
        


def get_OSM_edges_gdf(shapefile_path, OSM_folder, polygon=None, network_type= 'walk'):
    """
    If studyregion gdf file exist:
    Load a (projected) edge shapefile from disk 
    
    Else: query OSM to get the network gdf.

    Parameters
    ----------
    shapefile_path : string
        the name of the shapefile path(including file extension)
    OSM_folder : string
        the folder containing the OSM file, if None, use default data folder
    polygon : shapely Polygon or MultiPolygon
        the shape to get network data within. coordinates should be in units of
        latitude-longitude degrees.
    network_type : string
        what type of street network to get. Default type is pedestrain network  

    Returns
    -------
    GeoDataFrame
    """
    if os.path.exists(shapefile_path):
        edges = gpd.GeoDataFrame.from_file(shapefile_path)
    else:
        G = ox.graph_from_polygon(polygon, network_type=network_type, retain_all = True)
        G_proj = ox.project_graph(G)
        edges = ox.graph_to_gdfs(G_proj, nodes=False, edges=True, fill_edge_geometry=True)
    return edges
################################################################################



# Load OSM network stats
# This function retains all the basic stats for all streets, pedestrain network, and cycle network within 10km buffered study regions. The OSM street network data are loaded from local data folder.

def load_OSM_stats(G_filename, folder=OSM_folder):
    """
    retains all the basic stats for all, pedestrain network, and 
    cycle network within study regions graphml from a local folder
    
    Parameters
    ----------
    G_filename : string
        the name of the graphml file (including file extension)
    OSM_folder : string
        the folder containing the OSM file, if None, use default data folder
    
    
    Returns
    -------
    DataFrame
    """
    df = pd.DataFrame()
    #load street network data from local directory
    for networktype in ['all', 'walk', 'bike']:
        G = ox.load_graphml(G_filename, folder=folder)
        
        gdf_nodes_proj = ox.graph_to_gdfs(G_proj, edges=False)
        graph_area_m = gdf_nodes_proj.unary_union.convex_hull.area
        
        stats = ox.basic_stats(G_proj, area=graph_area_m, clean_intersects=True, circuity_dist='euclidean', tolerance=15)
        df1 = pd.DataFrame.from_dict(stats, orient='index', columns=[networktype + '_' + place])
        df = pd.concat([df, df1], axis=1)
    return df
    