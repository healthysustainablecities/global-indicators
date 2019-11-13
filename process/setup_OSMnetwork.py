get_nearest_node_to_pois################################################################################
# Script:  setup_OSMnetwork.py
# Purpose: Set up study region street networks
# Author:  Shirley Liu
# Date:    201908
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
from config import *

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
def Save_OSM_G(polygon, network_type= 'walk', placename=placename, suffix=suffix, folder=OSM_folder):    
    """
    save a graphml from a single polygon.
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
    ox.plot_graph(G)


def Save_OSM_G_proj(placename=placename, network_type= 'walk', suffix=suffix, folder=OSM_folder, to_crs=None):    
    """
    save a projected graphml from graphml file
    Parameters
    ----------
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
    G = ox.load_graphml(filename='{studyregion}_{network_type}{suffix}.graphml'.format(
        studyregion = placename, network_type=network_type, suffix = suffix), folder=folder)
    #set up project projection, and save the projected graph (project to UTM so we can use metres as a unit when buffering)
    G_proj = ox.project_graph(G, to_crs=to_crs)
    ox.save_graphml(G_proj, filename='{studyregion}_proj_{network_type}{suffix}.graphml'.format(
        studyregion = placename, network_type=network_type, suffix = suffix), folder=folder)
    ox.plot_graph(G_proj)
    


def Save_OSM_gdf_proj(placename=placename, network_type= 'walk', suffix=suffix, folder=OSM_folder):    
    """
    save a projected geodataframe from a projected graphml file
    Parameters
    ----------
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
    G_proj = ox.load_graphml(filename='{studyregion}_proj_{network_type}{suffix}.graphml'.format(
        studyregion = placename, network_type=network_type, suffix = suffix), folder=folder)
    
    #save projected network geodataframe as shapefile (project to UTM so we can use metres as a unit when buffering)
    edges_proj_gdfs = ox.graph_to_gdfs(G_proj, nodes=False, edges=True, fill_edge_geometry=True)
    ox.save_gdf_shapefile(edges_proj_gdfs, filename='{studyregion}_proj_{network_type}{suffix}'.format(
        studyregion = placename, network_type=network_type, suffix = suffix), folder=folder)
    
    #show network figure
    fig, ax = plt.subplots(figsize=(5, 5))
    ax = edges_proj_gdfs.plot(ax=ax)
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

def load_OSM_basic_stats(G_filename, folder=OSM_folder):
    """
    retains all the basic stats for pedestrain network within study regions graphml from a local folder
    
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
    G = ox.load_graphml(G_filename, folder=folder)
        
    gdf_nodes = ox.graph_to_gdfs(G, edges=False)
    graph_area_m = gdf_nodes.unary_union.convex_hull.area
        
    stats = ox.basic_stats(G, area=graph_area_m, clean_intersects=True, circuity_dist='euclidean', tolerance=15)
    df1 = pd.DataFrame.from_dict(stats, orient='index', columns=['OSM_pedestrain_network'])
    df = pd.concat([df, df1], axis=1)
    return df
################################################################################


def get_osm_pois_gdf(poi_filepath, shop, bbox):
    """
    retains open street map point of interest data
    
    Parameters
    ----------
    poi_filepath : string
        point of interest filepath
    shop : list
        list of OSM tag for shops
    bbox : list
        study region bounding box geometry
    

    Returns
    -------
    DataFrame
    """
    if os.path.isfile(poi_filepath):
        # if a points-of-interest file already exists, just load the dataset from that
        pois = pd.read_csv(poi_filepath)
        method = 'loaded from CSV'
    else:   
        # otherwise, query the OSM API for the specified amenities within the bounding box 
        osm_tags = '"shop"~"{}"'.format('|'.join(shop))
        pois = osm.node_query(bbox[0], bbox[1], bbox[2], bbox[3], tags=osm_tags)

        # drop any that aren't just 'shop' then save to CSV
        pois = pois[pois['shop'].isin(shop)]
        pois.to_csv(poi_filepath, index=False, encoding='utf-8')
        method = 'downloaded from OSM'
    pois_df = pois[['shop', 'name', 'lat', 'lon']]
    pois_df['geometry'] = pois_df.apply(lambda row: Point(row['lon'], row['lat']), axis=1)
    pois_gdf = gpd.GeoDataFrame(pois_df)
    return pois_gdf
    