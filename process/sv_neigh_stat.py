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
import sv_config as sc
import os
import sv_setup_local_analysis as ssl

# read projected graphml
dirname = os.path.dirname(__file__)
graphmlProj_path = os.path.join(dirname, sc.folder, sc.graphmlProj_name)
if os.path.isfile(graphmlProj_path):
    G_proj = ox.load_graphml(graphmlProj_path)
else:
    # else read original graphml and reproject it
    graphml_path = os.path.join(dirname, sc.graphmlPath)
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
sampleData = gpd.read_file(gpkgPath, layer=sc.samplePoints)

# method 1: apply method took 520s to process 530 sample points
df_result = sampleData['geometry'].apply(ssl.neigh_stats_apply,
                                         args=(
                                             G_proj,
                                             hex250,
                                             1600,
                                         ))

# method2: iterrows took 540s to process 530 sample points
# df_result = ssl.neigh_stats_iterrows(sampleData, G_proj, hex250, 1600)

# Concatenate the average of population and intersections back to the df of sample points
sampleData = pd.concat([sampleData, df_result], axis=1)





# save output to a new geopackage
# output_gpkgPath = os.path.join(dirname, sc.output_gpkgPath)
# gdf.to_file(output_gpkgPath, layer='sampelpoints',driver='GPKG')
