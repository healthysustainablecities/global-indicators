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

#----------------------------------------------------------------------------
# method 1: apply method took 520s to process 530 sample points
# !!!!! change the argument 200 to 1600 for production
df_result = samplePointsData['geometry'].apply(ssl.neigh_stats_apply,
                                               args=(
                                                   G_proj,
                                                   hex250,
                                                   200,
                                               ))
# Concatenate the average of population and intersections back to the df of sample points
samplePointsData = pd.concat([samplePointsData, df_result], axis=1)
samplePointsData.to_file(gpkgPath, layer='samplePointsData_temp', driver='GPKG')

# # method2: iterrows took 540s to process 530 sample points
# # df_result = ssl.neigh_stats_iterrows(samplePointsData, G_proj, hex250, 1600)

# # method3: try to use vetorize in pandas(failed, may be not suitable)
# # https://engineering.upside.com/a-beginners-guide-to-optimizing-pandas-code-for-speed-c09ef2c6a4d6
# # df_result = ssl.neigh_stats_apply(samplePointsData['geometry'],G_proj,hex250,200)

# # method4: try to use rtree method in shapely to intersect(failed, only work when length is shorter.)
# # https://stackoverflow.com/questions/14697442/faster-way-of-polygon-intersection-with-shapely
# # https://geoffboeing.com/2016/10/r-tree-spatial-index-python/

# # method5: try to use multiprocessing, or GPU to calculate
#----------------------------------------------------------------------------

#----------------------------------------------------------------------------
#Calculate accessibility to POI(supermarket,convenience,pt,pso)
# create the pandana network, just use nodes and edges
gdf_nodes, gdf_edges = ox.graph_to_gdfs(G_proj)
net = ssl.create_pdna_net(gdf_nodes, gdf_edges)

# get distance from "destination" layer
gdf_poi1 = gpd.read_file(gpkgPath, layer=sc.destinations)
poi_names = [sc.supermarket, sc.convenience, sc.PT]
gdf_poi_dist1 = ssl.cal_dist2poi(gdf_poi1, net, *(poi_names))

# get distance from "aos_nodes_30m_line" layer
gdf_poi2 = gpd.read_file(gpkgPath, layer=sc.pos)
# filterattr=False to indicate the layer is "aos_nodes_30m_line"
gdf_poi_dist2 = ssl.cal_dist2poi(gdf_poi2, net, sc.pos, filterattr=False)

gdf_nodes_poi_dist = pd.concat([gdf_nodes, gdf_poi_dist1, gdf_poi_dist2],
                               axis=1)

# convert distance of each nodes to binary index
poi_names.append(sc.pos)
gdf_nodes_poi_dist = ssl.convert2binary(gdf_nodes_poi_dist, *poi_names)
# set index of gdf_nodes_poi_dist to use 'osmid' as index
gdf_nodes_poi_dist.set_index('osmid', inplace=True, drop=False)
gdf_nodes_poi_dist.to_file(gpkgPath, layer='gdf_nodes_poi_dist', driver='GPKG')

# drop unuseful columns
gdf_nodes_poi_dist.drop(['geometry', 'id', 'lat', 'lon', 'y', 'x', 'highway'],
                        axis=1,
                        inplace=True)

# join the fields in the table of nodes table to the table of sample points
# for each sample point, create a new field to save the osmid of  the closest point
samplePointsData['closest_node_id'] = np.where(
    samplePointsData.n1_distance <= samplePointsData.n2_distance,
    samplePointsData.n1, samplePointsData.n2)

# join the two tables based on node id (sample point, nodes: one to many)
samplePointsData['closest_node_id'] = samplePointsData[
    'closest_node_id'].astype(int)
samplePointsData = samplePointsData.join(gdf_nodes_poi_dist,
                                         on='closest_node_id',
                                         how='left',
                                         rsuffix='_nodes')

# drop the nan rows in based on 'sp_nearest_node_{0}_binary' and 'sp_local_nh_avg_pop_density'
samplePointsData.dropna(inplace=True)

# create new field for living score
samplePointsData['sp_daily_living_score'] = (
    samplePointsData['sp_nearest_node_{0}_binary'.format(poi_names[0])] +
    samplePointsData['sp_nearest_node_{0}_binary'.format(poi_names[1])] +
    samplePointsData['sp_nearest_node_{0}_binary'.format(poi_names[2])] +
    samplePointsData['sp_nearest_node_{0}_binary'.format(poi_names[3])])

oriFieldNames = [
    'sp_local_nh_avg_pop_density', 'sp_local_nh_avg_intersection_density',
    'sp_daily_living_score'
]
newFieldNames = [
    'sp_zscore_local_nh_avgpopdensity', 'sp_zscore_local_nh_avgintdensity',
    'sp_zscore_daily_living_score'
]

fieldNames = list(zip(oriFieldNames, newFieldNames))
samplePointsData = ssl.cal_zscores(samplePointsData, fieldNames)

# sum these three zscores for walkability
samplePointsData['sp_walkability_index'] = samplePointsData[newFieldNames].sum(
    axis=1)

samplePointsData.to_file(gpkgPath, layer='samplePointsData', driver='GPKG')

print('Time is: {}'.format(time.time() - startTime))

# save output to a new geopackage
# output_gpkgPath = os.path.join(dirname, sc.output_gpkgPath)
# gdf.to_file(output_gpkgPath, layer='sampelpoints',driver='GPKG')
