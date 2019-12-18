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
import sv_setup_sample_analysis_new1 as sss
import time
from multiprocessing import Pool, cpu_count, Value, Manager, Process, Queue
from functools import partial
import json

startTime = time.time()
dirname = os.path.abspath('')
# change the json file location for every city
jsonFile = "./configuration/melbourne.json"
jsonPath = os.path.join(dirname, 'process', jsonFile)
with open(jsonPath) as json_file:
    config = json.load(json_file)

# read projected graphml
graphmlProj_path = os.path.join(dirname, config["folder"],
                                config["graphmlProj_name"])
if os.path.isfile(graphmlProj_path):
    print('being to read network.')
    G_proj = ox.load_graphml(graphmlProj_path)
else:
    # else read original graphml and reproject it
    print('begin to reproject network')
    graphml_path = os.path.join(dirname, config["folder"],
                                config["graphmlName"])
    G = ox.load_graphml(graphml_path)
    G_proj = ox.project_graph(G, to_crs=config["to_crs"])
    ox.save_graphml(G_proj,
                    filename=config["graphmlProj_name"],
                    folder=os.path.join(dirname, config["folder"]))

# output gpkg for sample points to the same gpkg
gpkgPath = os.path.join(dirname, config["folder"], config["geopackagePath"])
hex250 = gpd.read_file(gpkgPath, layer=config["parameters"]["hex250"])
# create nodes from G_proj
gdf_nodes = ox.graph_to_gdfs(G_proj, nodes=True, edges=False)
gdf_nodes.osmid = gdf_nodes.osmid.astype(int)
gdf_nodes = gdf_nodes.drop_duplicates(subset='osmid')
gdf_nodes_simple = gdf_nodes[['osmid']].copy()
del gdf_nodes

print('begin to calculate average poplulation and intersection density.')
distance = config['parameters']['search_distance']
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
    return data_subset['osmid'].apply(func,
                                      args=(G_proj, hex250, pop_density,
                                            intersection_density, distance,
                                            val, rows))


def parallelize_on_rows(data, func, num_of_processes=8):
    return parallelize(data, partial(run_on_subset, func), num_of_processes=8)


val = Value('i', 0)
rows = gdf_nodes_simple.shape[0]
# sindex = hex250.sindex
# # method 1: single thread
# df_result = gdf_nodes_simple['osmid'].apply(sss.neigh_stats_apply,
#                                             args=(G_proj, hex250, pop_density,
#                                                   intersection_density,
#                                                   distance, val, rows))
# # Concatenate the average of population and intersections back to the df of sample points
# gdf_nodes_simple = pd.concat([gdf_nodes_simple, df_result], axis=1)

# # method2 : use multiprocessing, not stable, could cause memory leak
# sindex = hex250.sindex
# df_result = parallelize_on_rows(gdf_nodes_simple, sss.neigh_stats_apply,
#                                 cpu_count() - 1)
# gdf_nodes_simple = pd.concat([gdf_nodes_simple, df_result], axis=1)

# # method3: other way to use multiprocessing
# node_list = gdf_nodes_simple.osmid.tolist()
# node_list.sort()
# cpus = cpu_count()
# results = []
# nodes = sss.split_list(node_list, 1000)
# for i, nodes_part in enumerate(nodes):
#     print("loop: {} / 1000".format(i+1))
#     with Manager() as manager:
#         L = manager.list()
#         processes = []
#         nodes_all = sss.split_list(nodes_part, cpus)
#         for i in range(cpus):
#             p = Process(target=sss.neigh_stats,
#                         args=(G_proj, hex250, distance, val, rows, L, nodes_all[i]))
#             p.start()
#             processes.append(p)
#         for p in processes:
#             p.join()
#         x = list(L)
#         results = results + x
# gdf_nodes_simple = pd.DataFrame(
#     results, columns=['osmid', pop_density, intersection_density])

# method4: other way to use multiprocessing
# apply and apply_async much slower than Process
results = []
node_list = gdf_nodes_simple.osmid.tolist()
node_list.sort()
nodes = sss.split_list(node_list, 5000)
for i, nodes_part in enumerate(nodes):
    print("loop: {} / 10000".format(i))
    nodes_all = sss.split_list(nodes_part, cpu_count())
    pool = Pool(cpu_count())
    result_objects = [
        pool.apply_async(sss.neigh_stats1,
                         args=(G_proj, hex250, distance, rows, nodes, index))
        for index, nodes in enumerate(nodes_all)
    ]
    for r in result_objects:
        results = results + r.get()
    pool.close()
    pool.join()
gdf_nodes_simple = pd.DataFrame(
    results, columns=['osmid', pop_density, intersection_density])

gdf_nodes_simple.to_csv(
    os.path.join(dirname, config["folder"], config['parameters']['tempCSV']))
# set osmid as index
gdf_nodes_simple.set_index('osmid', inplace=True, drop=False)
print('The time to finish average pop and intersection density is: {}'.format(
    time.time() - startTime))
# ----------------------------------------------------------------------------

samplePointsData = gpd.read_file(gpkgPath,
                                 layer=config["parameters"]["samplePoints"])

if "hex_id" not in samplePointsData.columns.tolist():
    # get sample point dataframe columns
    print("begin to create hex_id for sample points")
    samplePoint_column = samplePointsData.columns.tolist()
    samplePoint_column.append('index')

    # join id from hex to each sample point
    samplePointsData = gpd.sjoin(samplePointsData,
                                 hex250,
                                 how='left',
                                 op='within')
    samplePointsData = samplePointsData[samplePoint_column].copy()
    samplePointsData.rename(columns={'index': 'hex_id'}, inplace=True)
del hex250

print('begin to calculate assessbility to POIs.')
# Calculate accessibility to POI(supermarket,convenience,pt,pso)
# create the pandana network, just use nodes and edges
gdf_nodes, gdf_edges = ox.graph_to_gdfs(G_proj)
del G_proj
net = sss.create_pdna_net(gdf_nodes, gdf_edges)

# get distance from "destination" layer
gdf_poi1 = gpd.read_file(gpkgPath, layer=config["parameters"]["destinations"])
poi_names = [
    config["parameters"]["supermarket"], config["parameters"]["convenience"],
    config["parameters"]["PT"]
]
distance = config["parameters"]["accessibility_distance"]
output_fieldNames1 = [
    config["samplePoint_fieldNames"]["sp_nearest_node_supermarket_dist"],
    config["samplePoint_fieldNames"]["sp_nearest_node_convenience_dist"],
    config["samplePoint_fieldNames"]["sp_nearest_node_pt_dist"]
]

names1 = list(zip(poi_names, output_fieldNames1))

gdf_poi_dist1 = sss.cal_dist2poi(gdf_poi1, distance, net, *(names1))
del gdf_poi1
# get distance from "aos_nodes_30m_line" layer
gdf_poi2 = gpd.read_file(gpkgPath, layer=config["parameters"]["pos"])

names2 = [(config["parameters"]["pos"],
           config["samplePoint_fieldNames"]["sp_nearest_node_pos_dist"])]
# filterattr=False to indicate the layer is "aos_nodes_30m_line"
gdf_poi_dist2 = sss.cal_dist2poi(gdf_poi2,
                                 distance,
                                 net,
                                 *names2,
                                 filterattr=False)
del gdf_poi2
gdf_nodes_poi_dist = pd.concat([gdf_nodes, gdf_poi_dist1, gdf_poi_dist2],
                               axis=1)
del gdf_nodes, gdf_poi_dist1, gdf_poi_dist2
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
                                         rsuffix='_nodes1')
# join pop and intersection density from nodes to sample points
samplePointsData = samplePointsData.join(gdf_nodes_simple,
                                         on='closest_node_id',
                                         how='left',
                                         rsuffix='_nodes2')

# drop the nan rows samplePointsData, and deep copy to a new variable
samplePointsData_withoutNan = samplePointsData.dropna().copy()
nanData = samplePointsData[~samplePointsData.index.
                           isin(samplePointsData_withoutNan.index)]
nanData.to_file(gpkgPath, layer=config["parameters"]["dropNan"], driver='GPKG')
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

# # change field names to the disired ones
# samplePointsData_withoutNan.rename(columns={'index': 'hex_id'}, inplace=True)

samplePointsData_withoutNan.to_file(
    gpkgPath, layer=config["parameters"]["samplepointResult"], driver='GPKG')
endTime = time.time() - startTime
print('Total time is : {0:.2f} hours or {1:.2f} seconds'.format(
    endTime / 3600, endTime))
