"""
using osmnx and networkx to get the network within 1600m
"""

import osmnx as ox
import networkx as nx
from shapely.geometry import Point
import os
import numpy as np

G_proj = ox.load_graphml(
    r'C:\Users\zwa\Desktop\Project\5654_Global_Indicators_Project_RMIT\Data\phoenix_us_2019\test_area_OSM_Proj.graphml')
# ox.plot_graph(G_proj)

# the point is y,x !!!
orig_point = (3704517.52200, 399153.96370)

# must set the method, otherwise it uses unit of decimal degrees
orig_node = ox.get_nearest_node(
    G_proj, orig_point, method='euclidean', return_dist=True)
subgraph_proj = nx.ego_graph(
    G_proj, orig_node[0], radius=500, distance='length')
subgraph_gdf = ox.graph_to_gdfs(
    subgraph_proj, nodes=False, edges=True, fill_edge_geometry=True)

# !!!!! some of the rows in osmid is list, so we need to cast it to str, otherwise it cannot save as shapefile
subgraph_gdf.columns = subgraph_gdf.columns.astype(str)
subgraph_gdf['osmid'] = subgraph_gdf['osmid'].astype(str)
if len(subgraph_gdf) > 0:  # len() is a bit faster that df.empty
    subgraph_gdf[['osmid', 'geometry']].to_file(
        r'C:\Users\zwa\Desktop\Project\5654_Global_Indicators_Project_RMIT\Data\phoenix_us_2019\test_area_OSM_Proj.shp\sample_point_network\500network.shp')
