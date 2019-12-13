"""
Prepare all the fields for sample point

For the network within 1600m of each sample point, calculate the average 
densities for poplulation and intersections using the 250m hex 

# notice: must close the geopackage connection in QGIS.Otherwise, 
# an error occurred when reading
"""
import geopandas as gpd
import pandas as pd
import osmnx as ox
import numpy as np
import os
import sv_setup_sample_analysis as sss
import time
from multiprocessing import Pool, cpu_count
from functools import partial
import json

startTime = time.time()
dirname = os.path.dirname(__file__)
# change the json file location for every city
jsonFile = "./configuration/odense.json"
jsonPath = os.path.join(dirname, jsonFile)
with open(jsonPath) as json_file:
    config = json.load(json_file)

# read projected graphml
graphmlProj_path = os.path.join(dirname, config["folder"],
                                config["graphmlProj_name"])
if os.path.isfile(graphmlProj_path):
    G_proj = ox.load_graphml(graphmlProj_path)
else:
    # else read original graphml and reproject it
    graphml_path = os.path.join(dirname, config["folder"],
                                config["graphmlName"])
    G = ox.load_graphml(graphml_path)
    G_proj = ox.project_graph(G, to_crs=config["to_crs"])
    ox.save_graphml(G_proj,
                    filename=config["graphmlProj_name"],
                    folder=os.path.join(dirname, config["folder"]))

# output gpkg for sample points to the same gpkg
gpkgPath = os.path.join(dirname, config["folder"], config["geopackagePath"])
hex250 = gpd.read_file(gpkgPath, layer=config["parametres"]["hex250"])
samplePointsData = gpd.read_file(gpkgPath,
                                 layer=config["parametres"]["samplePoints"])

# get sample point dataframe columns
samplePoint_column = samplePointsData.columns.tolist()
samplePoint_column.append('index')

# join id from hex to each sample point
samplePointsData = gpd.sjoin(samplePointsData, hex250, how='left', op='within')
samplePointsData = samplePointsData[samplePoint_column].copy()
samplePointsData.rename(columns={'index': 'hex_id'}, inplace=True)

print('begin to calculate average poplulation and intersection density.')

#----------------------------------------------------------------------------
# # method 1: apply method took 520s to process 530 sample points
# # !!!!! change the argument 200 to 1600 for production
# df_result = samplePointsData['geometry'].apply(sss.neigh_stats_apply,
#                                                args=(
#                                                    G_proj,
#                                                    hex250,
#                                                    1600,
#                                                ))
# # Concatenate the average of population and intersections back to the df of sample points
# samplePointsData = pd.concat([samplePointsData, df_result], axis=1)
# samplePointsData.to_file(gpkgPath,
#                          layer='samplePointsData_temp',
#                          driver='GPKG')

# # method2: iterrows took 540s to process 530 sample points
# # df_result = sss.neigh_stats_iterrows(samplePointsData, G_proj, hex250, 1600)

# # method3: try to use vetorize in pandas(failed, may be not suitable)
# # https://engineering.upside.com/a-beginners-guide-to-optimizing-pandas-code-for-speed-c09ef2c6a4d6
# # df_result = sss.neigh_stats_apply(samplePointsData['geometry'],G_proj,hex250,200)

# # method4: try to use rtree method in shapely to intersect(failed, only work when length is shorter.)
# # https://stackoverflow.com/questions/14697442/faster-way-of-polygon-intersection-with-shapely
# # https://geoffboeing.com/2016/10/r-tree-spatial-index-python/

# method5: try to use multiprocessing, or GPU to calculate
distance = config['parametres']['search_distance']
pop_density = config['samplePoint_fieldNames']['sp_local_nh_avg_pop_density']
intersection_density = config['samplePoint_fieldNames'][
    'sp_local_nh_avg_intersection_density']


def parallelize(data, func, num_of_processes=8):
    data_split = np.array_split(data, num_of_processes)
    pool = Pool(num_of_processes)
    data = pd.concat(pool.map(func, data_split))
    pool.close()
    pool.join()
    return data


def run_on_subset(func, data_subset):
    return data_subset['geometry'].apply(func,
                                         args=(G_proj, hex250, pop_density,
                                               intersection_density, distance))


def parallelize_on_rows(data, func, num_of_processes=8):
    return parallelize(data, partial(run_on_subset, func), num_of_processes=8)


df_result = parallelize_on_rows(samplePointsData, sss.neigh_stats_apply,
                                cpu_count() - 1)

samplePointsData = pd.concat([samplePointsData, df_result], axis=1)
samplePointsData.to_file(gpkgPath,
                         layer=config["parametres"]["tempLayer"],
                         driver='GPKG')
#----------------------------------------------------------------------------
print('The time to finish average pop and intersection density is: {}'.format(
    time.time() - startTime))

#----------------------------------------------------------------------------
print('begin to calculate assessbility to POIs.')
#Calculate accessibility to POI(supermarket,convenience,pt,pso)
# create the pandana network, just use nodes and edges
gdf_nodes, gdf_edges = ox.graph_to_gdfs(G_proj)
net = sss.create_pdna_net(gdf_nodes, gdf_edges)

# get distance from "destination" layer
gdf_poi1 = gpd.read_file(gpkgPath, layer=config["parametres"]["destinations"])
poi_names = [
    config["parametres"]["supermarket"], config["parametres"]["convenience"],
    config["parametres"]["PT"]
]
distance = config["parametres"]["accessibility_distance"]
output_fieldNames1 = [
    config["samplePoint_fieldNames"]["sp_nearest_node_supermarket_dist"],
    config["samplePoint_fieldNames"]["sp_nearest_node_convenience_dist"],
    config["samplePoint_fieldNames"]["sp_nearest_node_pt_dist"]
]

names1 = list(zip(poi_names, output_fieldNames1))

gdf_poi_dist1 = sss.cal_dist2poi(gdf_poi1, distance, net, *(names1))

# get distance from "aos_nodes_30m_line" layer
gdf_poi2 = gpd.read_file(gpkgPath, layer=config["parametres"]["pos"])

names2 = [(config["parametres"]["pos"],
           config["samplePoint_fieldNames"]["sp_nearest_node_pos_dist"])]
# filterattr=False to indicate the layer is "aos_nodes_30m_line"
gdf_poi_dist2 = sss.cal_dist2poi(gdf_poi2,
                                 distance,
                                 net,
                                 *names2,
                                 filterattr=False)

gdf_nodes_poi_dist = pd.concat([gdf_nodes, gdf_poi_dist1, gdf_poi_dist2],
                               axis=1)

# convert distance of each nodes to binary index
output_fieldNames1.append(
    config["samplePoint_fieldNames"]["sp_nearest_node_pos_dist"])
output_fieldNames2 = [
    config["samplePoint_fieldNames"]["sp_nearest_node_supermarket_binary"],
    config["samplePoint_fieldNames"]["sp_nearest_node_convenience_binary"],
    config["samplePoint_fieldNames"]["sp_nearest_node_pt_binary"],
    config["samplePoint_fieldNames"]["sp_nearest_node_pos_binary"]
]
names3 = list(zip(output_fieldNames1, output_fieldNames2))
gdf_nodes_poi_dist = sss.convert2binary(gdf_nodes_poi_dist, *names3)
# set index of gdf_nodes_poi_dist to use 'osmid' as index
gdf_nodes_poi_dist.set_index('osmid', inplace=True, drop=False)

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

# drop the nan rows samplePointsData, and deep copy to a new variable
samplePointsData_withoutNan = samplePointsData.dropna().copy()
nanData = samplePointsData[~samplePointsData.index.
                           isin(samplePointsData_withoutNan.index)]
nanData.to_file(gpkgPath, layer=config["parametres"]["dropNan"], driver='GPKG')
del nanData

# create new field for living score,excluede public open space
output_fieldNames2.pop()
samplePointsData_withoutNan[
    'sp_daily_living_score'] = samplePointsData_withoutNan[
        output_fieldNames2].sum(axis=1)

oriFieldNames = [
    config["samplePoint_fieldNames"]["sp_local_nh_avg_pop_density"],
    config["samplePoint_fieldNames"]["sp_local_nh_avg_intersection_density"],
    config["samplePoint_fieldNames"]["sp_daily_living_score"]
]
newFieldNames = [
    config["samplePoint_fieldNames"]["sp_zscore_local_nh_avgpopdensity"],
    config["samplePoint_fieldNames"]["sp_zscore_local_nh_avgintdensity"],
    config["samplePoint_fieldNames"]["sp_zscore_daily_living_score"]
]

fieldNames = list(zip(oriFieldNames, newFieldNames))
samplePointsData_withoutNan = sss.cal_zscores(samplePointsData_withoutNan,
                                              fieldNames)

# sum these three zscores for walkability
samplePointsData_withoutNan[
    'sp_walkability_index'] = samplePointsData_withoutNan[newFieldNames].sum(
        axis=1)

# change field names to the disired ones
samplePointsData_withoutNan.rename(columns={'index': 'hex_id'}, inplace=True)

samplePointsData_withoutNan.to_file(
    gpkgPath, layer=config["parametres"]["samplepointResult"], driver='GPKG')

print('Total time is: {}'.format(time.time() - startTime))
