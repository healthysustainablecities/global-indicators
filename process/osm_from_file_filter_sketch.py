# Libraries used for OSM conversion
import os
import sys
import subprocess as sp
from datetime import datetime

# Libraries used for OSMnx analyses and output
import networkx as nx
import osmnx as ox
import requests
import fiona
ox.config(use_cache=True, log_console=True)
ox.__version__

from shapely.geometry import shape, MultiPolygon, Polygon

# location of source OSM file
dir = 'D:/osm/planet_archives/planet-latest_20181001.osm.pbf'
  
# location of boundary files to iterate over
search_dir = 'D:/ntnl_li_2018_template/data/21Cities/OSM_Roads'


# define pedestrian network custom filter (based on OSMnx 'walk' network type, without the cycling exclusion)
pedestrian = (
             '["area"!~"yes"]' 
             '["highway"!~"motor|proposed|construction|abandoned|platform|raceway"]'
             '["foot"!~"no"]'  
             '["service"!~"private"]' 
             '["access"!~"private"]'
             )


def format_filter_list(custom_filter):
    """
    Reformat a filter into a list for filtering JSON generated from an OSM file.
    
    Parameters
    ----------
    custom_filter : string
        a custom network filter to be used instead of the network_type presets, following OSMnx (Overpass) format

    Returns
    -------
    filter_list list
    """
    # remove quotes
    custom_filter = custom_filter.replace('"', '')
    # remove the initial brackets
    custom_filter = custom_filter[1:-1]
    # create as list of kv pair strings          
    custom_filter = custom_filter.split("][")
    # split into list of kv tuples
    custom_filter = [x.split("!~") for x in custom_filter]
    # expand values as list
    filter_list = [[x[0],x[1].split('|')] for x in custom_filter]
    return(filter_list)

    
def check_filter_list(element, filter_list, attribute = 'tags'):
    """
    Check a set of restricted key value tags against a filter list and return a boolean check against non-presence
    
    Parameters
    ----------
    element: dict
        an OSM element, containing 'type' and 'tags' dictionaires
    filter_list : list of 2-tuples
        a filter list of key value pairs which should not be found in a list of tags
    attribute : string
        the name of the dictionary in which to check for key-value pairs

    Returns
    -------
    keep boolean
    """
    check = 0
    for test in filter_list:
        reject = 0
        key = test[0]
        value_list = test[1]
        reject += (0, 1)[(key in element[attribute] and element[attribute][key] in value_list) == True]
        # print('({key} in tags and tags[{key}] not in {values}) == {reject}'.format(key = key, 
        #                                                                              values = value_list,
        #                                                                             reject = reject))
        check+=reject
    keep = check < 1
    return(keep)    
    
filter_list = format_filter_list(pedestrian)              


data = [ox.overpass_json_from_file('D:/ntnl_li_2018_template/data/21Cities/OSM_Roads/AlburyWodonga/AlburyWodonga.osm')]
# Format of data is as per http://overpass-api.de/output_formats.html#json

len(data)
# 3

data.keys()
# dict_keys(['elements', 'version', 'generator'])

# We are interested in 'elements'
len(data['elements'])
# 262586

len(data['elements'][0])
# 9

data['elements'][0]
# {'type': 'node', 'tags': {}, 'nodes': [], 'id': 25637355, 'lat': -36.0804138, 'lon': 146.9131031, 'version': 31, 'timestamp': '2014-10-28T23:04:17Z', 'changeset': 0}

l = data['elements'][5]

check_filter_list(l,filter_list)

# full logic
keep = [x for x in data['elements'] if 
        (("area"    in x['tags'] and x['tags']["area"   ] not in ["yes"]) or
        ("highway"  in x['tags'] and x['tags']["highway"] not in ["motor","proposed","construction","abandoned","platform","raceway"]) or
        ("foot"     in x['tags'] and x['tags']["foot"   ] not in ["no"]) or
        ("service"  in x['tags'] and x['tags']["service"] not in ["private"]) or
        ("access"   in x['tags'] and x['tags']["access" ] not in ["private"])) 
        or x['tags']=={}
        ]

reject = [x for x in data['elements'] if 
          (("area"    in x['tags'] and x['tags']["area"   ] in ["yes"]) or
          ("highway"  in x['tags'] and x['tags']["highway"] in ["motor","proposed","construction","abandoned","platform","raceway"]) or
          ("foot"     in x['tags'] and x['tags']["foot"   ] in ["no"]) or
          ("service"  in x['tags'] and x['tags']["service"] in ["private"]) or
          ("access"   in x['tags'] and x['tags']["access" ] in ["private"]))]

# abstracted logic
keep = [x for x in data['elements'] if check_filter_list(x,filter_list) or x['tags']=={}]
reject = [x for x in data['elements'] if check_filter_list(x,filter_list) is False]

# redefined osmnx graph from file, allowing for filtering 

def graph_from_file_filtered(filename, 
                             network_type='all_private', 
                             simplify=True,
                             retain_all=False, 
                             name='unnamed',
                             custom_filter=None):
    """
    Create a networkx graph from OSM data in an XML file.

    Parameters
    ----------
    filename : string
        the name of a file containing OSM XML data
    network_type : string
        what type of street network to get
    custom_filter : string
        a custom network filter to be used instead of the network_type presets, following OSMnx (Overpass) format
    simplify : bool
        if true, simplify the graph topology
    retain_all : bool
        if True, return the entire graph even if it is not connected
    name : string
        the name of the graph

    Returns
    -------
    networkx multidigraph
    """
    # transmogrify file of OSM XML data into JSON
    response_jsons = [ox.overpass_json_from_file(filename)]
    
    if custom_filter is not None:
        filter_list = format_filter_list(custom_filter)
        response_jsons[0]['elements'] = [x for x in response_jsons[0]['elements'] if x['type'] in ['way','node'] and (check_filter_list(x,filter_list) or x['tags']=={})]
    
    # create graph using this response JSON
    G = ox.create_graph(response_jsons, 
                     network_type=network_type,
                     retain_all=retain_all, name=name)
    
    # simplify the graph topology as the last step.
    if simplify:
        G = ox.simplify_graph(G)
    
    log('graph_from_file() returning graph with {:,} nodes and {:,} edges'.format(len(list(G.nodes())), len(list(G.edges()))))
    return G    
    
G = graph_from_file_filtered(filename='D:/ntnl_li_2018_template/data/21Cities/OSM_Roads/AlburyWodonga/AlburyWodonga.osm',
                             custom_filter=pedestrian)
                             
filename='D:/ntnl_li_2018_template/data/21Cities/OSM_Roads/AlburyWodonga/AlburyWodonga.osm'  
custom_filter=pedestrian    
name = 'unnamed'                       
network_type='walk'
retain_all=False
response_jsons = [ox.overpass_json_from_file(filename)]
filter_list = format_filter_list(custom_filter)
response_jsons[0]['elements'] = [x for x in response_jsons[0]['elements'] if x['type'] in ['way','node'] and (check_filter_list(x,filter_list) or x['tags']=={})]
# make sure we got data back from the server requests
elements = []
for response_json in response_jsons:
    elements.extend(response_json['elements'])
if len(elements) < 1:
    raise EmptyOverpassResponse('There are no data elements in the response JSON objects')

# create the graph as a MultiDiGraph and set the original CRS to default_crs
G = nx.MultiDiGraph(name=name, crs=ox.settings.default_crs)

# extract nodes and paths from the downloaded osm data
nodes = {}
paths = {}
for osm_data in response_jsons:
    nodes_temp, paths_temp = ox.parse_osm_nodes_paths(osm_data)
    for key, value in nodes_temp.items():
        nodes[key] = value
    for key, value in paths_temp.items():
        paths[key] = value

# add each osm node to the graph
for node, data in nodes.items():
    G.add_node(node, **data)

# add each osm way (aka, path) to the graph
G = ox.add_paths(G, paths, network_type)

# retain only the largest connected component, if caller did not
# set retain_all=True
if not retain_all:
    G = ox.get_largest_component(G)

ox.log('Created graph with {:,} nodes and {:,} edges in {:,.2f} seconds'.format(len(list(G.nodes())), len(list(G.edges())), time.time()-start_time))

# add length (great circle distance between nodes) attribute to each edge to
# use as weight
if len(G.edges) > 0:
    G = ox.add_edge_lengths(G)                             


#def add_edge_lengths(G):
#"""
#Add length (meters) attribute to each edge by great circle distance between
#nodes u and v.
#
#Parameters
#----------
#G : networkx multidigraph
#
#Returns
#-------
#G : networkx multidigraph
#"""

start_time = time.time()

# first load all the edges' origin and destination coordinates as a
# dataframe indexed by u, v, key

import numpy as np
import pandas as pd
# this is what the line should be, but gets a key error for some reason which i can't see
coords = np.array([[u, v, k, G.nodes[u]['y'], G.nodes[u]['x'], G.nodes[v]['y'], G.nodes[v]['x']] for u, v, k in G.edges(keys=True)])

# work around
coords = [[u, v, k, G.nodes[u], G.nodes[u], G.nodes[v], G.nodes[v]] for u, v, k in G.edges(keys=True)]
coords = np.array([[x[0],x[1],x[2],x[3]['y'],x[3]['x'],x[4]['y'],x[4]['x']] for x in coords if 'y' in x[3]])

df_coords = pd.DataFrame(coords, columns=['u', 'v', 'k', 'u_y', 'u_x', 'v_y', 'v_x'])
df_coords[['u', 'v', 'k']] = df_coords[['u', 'v', 'k']].astype(np.int64)
df_coords = df_coords.set_index(['u', 'v', 'k'])

# then calculate the great circle distance with the vectorized function
gc_distances = ox.great_circle_vec(lat1=df_coords['u_y'],
                                lng1=df_coords['u_x'],
                                lat2=df_coords['v_y'],
                                lng2=df_coords['v_x'])

# fill nulls with zeros and round to the millimeter
gc_distances = gc_distances.fillna(value=0).round(3)
nx.set_edge_attributes(G, name='length', values=gc_distances.to_dict())

log('Added edge lengths to graph in {:,.2f} seconds'.format(time.time()-start_time))
return G    