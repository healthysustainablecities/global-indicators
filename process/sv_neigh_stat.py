"""
For the network within 1600m of each sample point, calculate the average 
densities for poplulation and intersections using the 250m hex 

# notice: must close the geopackage connection in QGIS.Otherwise, 
# an error occurred when reading
"""
import geopandas as gpd
import pandas as pd
import osmnx as ox
import networkx as nx
import pandana as pdna
import numpy as np
import sv_config as sc
import os
import sv_setup_local_analysis as ssl
import time
startTime = time.time()
# read projected graphml
dirname = os.path.dirname(__file__)
graphmlProj_path = os.path.join(dirname, sc.folder, sc.graphmlProj_name)
if os.path.isfile(graphmlProj_path):
    G_proj = ox.load_graphml(graphmlProj_path)
else:
    # else read original graphml and reproject it
    graphml_path = os.path.join(dirname, sc.graphmlName)
    G = ox.load_graphml(graphml_path)
    G_proj = ox.project_graph(G, to_crs=sc.to_crs)
    ox.save_graphml(G_proj,
                    filename=sc.graphmlProj_name,
                    folder=os.path.join(dirname, sc.folder))

# load projected nodes and edges from geopackage, and convert them to a graph
# gpkgPath = os.path.join(dirname, sc.geopackagePath)
# gdf_nodes = gpd.read_file(gpkgPath,layer=sc.nodes)
# gdf_nodes['x'] = gdf_nodes['geometry'].apply(lambda x: x.x)
# gdf_nodes['y'] =gdf_nodes['geometry'].apply(lambda x: x.y)
# gdf_edges = gpd.read_file(gpkgPath,layer=sc.edges)
# gdf_edges['u'] = gdf_edges['from']
# gdf_edges['v'] = gdf_edges['to']
# #!! an error occurred at this step, tried to fix that but failed.
# # Read original graphml file and reprojected it.
# G = ox.gdfs_to_graph(gdf_nodes,gdf_edges)

gpkgPath = os.path.join(dirname, sc.geopackagePath)
hex250 = gpd.read_file(gpkgPath, layer=sc.hex250)
samplePointsData = gpd.read_file(gpkgPath, layer=sc.samplePoints)

# method 1: apply method took 520s to process 530 sample points
# df_result = samplePointsData['geometry'].apply(ssl.neigh_stats_apply,
#                                                args=(
#                                                    G_proj,
#                                                    hex250,
#                                                    200,
#                                                ))

# method2: iterrows took 540s to process 530 sample points
# df_result = ssl.neigh_stats_iterrows(samplePointsData, G_proj, hex250, 1600)

# method3: try to use vetorize in pandas(failed, may be not suitable)
# https://engineering.upside.com/a-beginners-guide-to-optimizing-pandas-code-for-speed-c09ef2c6a4d6
# df_result = ssl.neigh_stats_apply(samplePointsData['geometry'],G_proj,hex250,200)

# method4: try to use rtree method in shapely to intersect
# https://stackoverflow.com/questions/14697442/faster-way-of-polygon-intersection-with-shapely

# Concatenate the average of population and intersections back to the df of sample points
# samplePointsData = pd.concat([samplePointsData, df_result], axis=1)

###################################
# Calculate accessibility to POI(supermarket,convenience,pt,pso)
# load nodes and egdes from Graphml
gdf_nodes, gdf_edges = ox.graph_to_gdfs(G_proj)
gdf_nodes['x'] = gdf_nodes['geometry'].apply(lambda x: x.x)
gdf_nodes['y'] = gdf_nodes['geometry'].apply(lambda x: x.y)
gdf_edges['from'] = gdf_edges['u'].astype(np.int64)
gdf_edges['to'] = gdf_edges['v'].astype(np.int64)
gdf_edges['length'] = gdf_edges['length'].astype(float)

gdf_nodes['id'] = gdf_nodes['osmid'].astype(np.int64)
gdf_nodes.set_index('id', inplace=True, drop=False)

net = pdna.Network(gdf_nodes['x'], gdf_nodes['y'], gdf_edges['from'],
                   gdf_edges['to'], gdf_edges[['length']])
net.precompute(300)

gdf_poi = gpd.read_file(gpkgPath, layer=sc.destinations)
gdf_poi['x'] = gdf_poi['geometry'].apply(lambda x: x.x)
gdf_poi['y'] = gdf_poi['geometry'].apply(lambda x: x.y)
net.set_pois("Supermarket", 200, 2, gdf_poi['x'], gdf_poi['y'])
dist = net.nearest_pois(200, "Supermarket", num_pois=2)
print(dist.columns)

# important to convert columns index tpye tot str
dist.columns = dist.columns.astype(str)
gdf_nodes_supermarket = pd.concat([gdf_nodes, dist], axis=1)
gdf_nodes_supermarket.to_file(gpkgPath,
                              layer='gdf_nodes_supermarket',
                              driver='GPKG')
print('Time is: {}'.format(time.time() - startTime))

# save output to a new geopackage
# output_gpkgPath = os.path.join(dirname, sc.output_gpkgPath)
# gdf.to_file(output_gpkgPath, layer='sampelpoints',driver='GPKG')
