# this script is used for testing pandana

import pandana as pdna
import osmnx as ox
import geopandas as gpd
import numpy as np
import pandas as pd

nodes = r'C:\Users\zwa\Desktop\Project\5654_Global_Indicators_Project_RMIT\Data\phoenix_us_2019\test_area_OSM_Proj.shp\nodes\nodes.shp'
edges = r'C:\Users\zwa\Desktop\Project\5654_Global_Indicators_Project_RMIT\Data\phoenix_us_2019\test_area_OSM_Proj.shp\edges\edges.shp'
poi = r'C:\Users\zwa\Desktop\Project\5654_Global_Indicators_Project_RMIT\Data\phoenix_us_2019\test_area_OSM_Proj.shp\poi\poi.shp'
gdf_nodes = gpd.read_file(nodes)
gdf_edges = gpd.read_file(edges)


gdf_nodes['x'] = gdf_nodes['geometry'].apply(lambda x: x.x)
gdf_nodes['y'] = gdf_nodes['geometry'].apply(lambda x: x.y)

# print(gdf_edges.iloc[0:1])
# print(gdf_edges.head(3))
# print(gdf_nodes.head(3))

# print(gdf_edges['from'])
gdf_edges['from'] = gdf_edges['from'].astype(np.int64)
gdf_edges['to'] = gdf_edges['to'].astype(np.int64)
gdf_edges['length'] = gdf_edges['length'].astype(float)
# print(gdf_edges['from'])

# ！must use the osmid as index for df
gdf_nodes['id'] = gdf_nodes['osmid'].astype(np.int64)
gdf_nodes.set_index('id', inplace=True, drop=False)

net = pdna.Network(gdf_nodes['x'], gdf_nodes['y'],
                   gdf_edges['from'], gdf_edges['to'], gdf_edges[['length']])
net.precompute(300)

gdf_poi = gpd.read_file(poi)
net.set_pois("restaurants", 200, 2, gdf_poi['X'], gdf_poi['Y'])
dist = net.nearest_pois(200, "restaurants", num_pois=2)
print(dist.columns)
dist.columns = dist.columns.astype(str)
result = pd.concat([gdf_nodes,dist],axis=1)

# nodes_pois = dist[[1]]
# result = pd.merge(left=gdf_nodes, right=nodes_pois, how='left', left_index=True, right_index=True)
result.to_file(r'C:\Users\zwa\Desktop\Project\5654_Global_Indicators_Project_RMIT\Data\phoenix_us_2019\test_area_OSM_Proj.shp\poi\pandana.shp')
