"""
This script is for preparing all the fields for sample points
All the cities should run this script first to get the pre-prepared sample points
before running the aggregation.

notice: must close the geopackage connection in QGIS.Otherwise, an error occurred when reading
"""
import geopandas as gpd
import pandas as pd
import osmnx as ox
import numpy as np
import os
import sv_setup_sp as sss
import time
from multiprocessing import Pool, cpu_count, Value, Manager, Process
from functools import partial
import json
import sys

if __name__ == '__main__':
    # use the script from command line, like "python process/sv_sp.py odense.json"
    startTime = time.time()

    # get the work directory
    dirname = os.path.abspath('')

    # the configuration file should put in the "/configuration" folder located at the same folder as scripts
    jsonFile = "./configuration/" + sys.argv[1]
    jsonPath = os.path.join(dirname, 'process', jsonFile)
    try:
        with open(jsonPath) as json_file:
            config = json.load(json_file)
    except Exception as e:
        print('Failed to read json file.')
        print(e)

    # output the processing city name to users
    print('Start to process city: {}'.format(config["study_region"]))

    # read projected graphml
    graphmlProj_path = os.path.join(dirname, config["folder"],
                                    config["graphmlProj_name"])
    G_proj = sss.readGraphml(graphmlProj_path, config)

    #  geopackage path where to read all the required layers and save processing layers to it
    gpkgPath = os.path.join(dirname, config["folder"],
                            config["geopackagePath"])

    # hexes in memory
    hex250 = gpd.read_file(gpkgPath, layer=config["parameters"]["hex250"])

    # create nodes from G_proj
    gdf_nodes = ox.graph_to_gdfs(G_proj, nodes=True, edges=False)
    gdf_nodes.osmid = gdf_nodes.osmid.astype(int)
    gdf_nodes = gdf_nodes.drop_duplicates(subset='osmid')
    gdf_nodes_simple = gdf_nodes[['osmid']].copy()
    del gdf_nodes

    print('Start to calculate average poplulation and intersection density.')

    # read search distance from json file, which should be 1600m
    distance = config['parameters']['search_distance']

    # read pop density and intersection density filed names from json file
    pop_density = config['samplePoint_fieldNames'][
        'sp_local_nh_avg_pop_density']
    intersection_density = config['samplePoint_fieldNames'][
        'sp_local_nh_avg_intersection_density']

    rows = gdf_nodes_simple.shape[0]

    # if provide 'true' in command line, then using multiprocessing, otherwise, using single thread
    # Notice: Meloubrne has the largest number of sample points, which needs 13 GB memory for docker using 3 cpus.
    if len(sys.argv) > 2:
        if sys.argv[2].lower() == "true":
            # method1: new way to use multiprocessing
            node_list = gdf_nodes_simple.osmid.tolist()
            node_list.sort()
            pool = Pool(cpu_count())
            result_objects = pool.starmap_async(
                sss.neigh_stats,
                [(G_proj, hex250, distance, rows, node, index)
                 for index, node in enumerate(node_list)],
                chunksize=1000).get()
            pool.close()
            pool.join()
            gdf_nodes_simple = pd.DataFrame(
                result_objects,
                columns=['osmid', pop_density, intersection_density])

    else:
        # method 2: single thread, use pandas apply()
        # create counter for loop
        val = Value('i', 0)
        df_result = gdf_nodes_simple['osmid'].apply(
            sss.neigh_stats_apply,
            args=(G_proj, hex250, pop_density, intersection_density, distance,
                  val, rows))
        # Concatenate the average of population and intersections back to the df of sample points
        gdf_nodes_simple = pd.concat([gdf_nodes_simple, df_result], axis=1)

    # save the pop and intersection density to a CSV file
    gdf_nodes_simple.to_csv(
        os.path.join(dirname, config["folder"],
                     config['parameters']['tempCSV']))

    # set osmid as index
    gdf_nodes_simple.set_index('osmid', inplace=True, drop=False)
    print('The time to finish average pop and intersection density is: {}'.
          format(time.time() - startTime))

    # read sample point from geopackage
    samplePointsData = gpd.read_file(
        gpkgPath, layer=config["parameters"]["samplePoints"])

    # create 'hex_id' for sample point, if it not exists
    if "hex_id" not in samplePointsData.columns.tolist():
        samplePointsData = sss.createHexid(samplePointsData, hex250)

    # Calculate accessibility to POI(supermarket,convenience,pt,pso)
    print('Start to calculate assessbility to POIs.')

    # create the pandana network, just use nodes and edges
    gdf_nodes, gdf_edges = ox.graph_to_gdfs(G_proj)
    net = sss.create_pdna_net(gdf_nodes, gdf_edges)

    # read "destinations" layer from geopackage
    gdf_poi1 = gpd.read_file(gpkgPath,
                             layer=config["parameters"]["destinations"])

    # read field names from json file
    poi_names = [
        config["parameters"]["supermarket"],
        config["parameters"]["convenience"], config["parameters"]["PT"]
    ]

    # read distance from json file, which is 500m
    distance = config["parameters"]["accessibility_distance"]

    # read output field names from json file
    output_fieldNames1 = [
        config["samplePoint_fieldNames"]["sp_nearest_node_supermarket_dist"],
        config["samplePoint_fieldNames"]["sp_nearest_node_convenience_dist"],
        config["samplePoint_fieldNames"]["sp_nearest_node_pt_dist"]
    ]

    # zip the input and output field names
    names1 = list(zip(poi_names, output_fieldNames1))

    # calculate the distance from each node to POI
    gdf_poi_dist1 = sss.cal_dist2poi(gdf_poi1, distance, net, *(names1))

    # read "aos_nodes_30m_line" layer from geopackage
    gdf_poi2 = gpd.read_file(gpkgPath, layer=config["parameters"]["pos"])

    # read field names from json file
    names2 = [(config["parameters"]["pos"],
               config["samplePoint_fieldNames"]["sp_nearest_node_pos_dist"])]

    # calculate the distance from each node to public open space,
    # filterattr=False to indicate the layer is "aos_nodes_30m_line"
    gdf_poi_dist2 = sss.cal_dist2poi(gdf_poi2,
                                     distance,
                                     net,
                                     *names2,
                                     filterattr=False)

    # concatenate two dataframes into one
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
    gdf_nodes_poi_dist.drop(
        ['geometry', 'id', 'lat', 'lon', 'y', 'x', 'highway'],
        axis=1,
        inplace=True)

    # for each sample point, create a new field to save the osmid of the closest point,
    # which is used for joining to nodes
    samplePointsData['closest_node_id'] = np.where(
        samplePointsData.n1_distance <= samplePointsData.n2_distance,
        samplePointsData.n1, samplePointsData.n2)

    # join the two tables based on node id (join on sample points and nodes)
    samplePointsData['closest_node_id'] = samplePointsData[
        'closest_node_id'].astype(int)

    # first, join POIs results from nodes to sample points
    samplePointsData = samplePointsData.join(gdf_nodes_poi_dist,
                                             on='closest_node_id',
                                             how='left',
                                             rsuffix='_nodes1')

    # second, join pop and intersection density from nodes to sample points
    samplePointsData = samplePointsData.join(gdf_nodes_simple,
                                             on='closest_node_id',
                                             how='left',
                                             rsuffix='_nodes2')

    # drop the nan rows samplePointsData, and deep copy to a new variable
    samplePointsData_withoutNan = samplePointsData.dropna().copy()
    nanData = samplePointsData[~samplePointsData.index.
                               isin(samplePointsData_withoutNan.index)]

    # save the nan rows to a new layer in geopackage, in case someone will check it
    nanData.to_file(gpkgPath,
                    layer=config["parameters"]["dropNan"],
                    driver='GPKG')
    del nanData

    # create new field for living score, and exclude public open space
    output_fieldNames2.pop()
    samplePointsData_withoutNan[
        'sp_daily_living_score'] = samplePointsData_withoutNan[
            output_fieldNames2].sum(axis=1)

    oriFieldNames = [
        config["samplePoint_fieldNames"]["sp_local_nh_avg_pop_density"],
        config["samplePoint_fieldNames"]
        ["sp_local_nh_avg_intersection_density"],
        config["samplePoint_fieldNames"]["sp_daily_living_score"]
    ]
    newFieldNames = [
        config["samplePoint_fieldNames"]["sp_zscore_local_nh_avgpopdensity"],
        config["samplePoint_fieldNames"]["sp_zscore_local_nh_avgintdensity"],
        config["samplePoint_fieldNames"]["sp_zscore_daily_living_score"]
    ]

    # zip the old and new field names together as input, and calculate zscore
    fieldNames = list(zip(oriFieldNames, newFieldNames))
    samplePointsData_withoutNan = sss.cal_zscores(samplePointsData_withoutNan,
                                                  fieldNames)

    # sum these three zscores for walkability
    samplePointsData_withoutNan[
        'sp_walkability_index'] = samplePointsData_withoutNan[
            newFieldNames].sum(axis=1)

    # save the sample points with all the desired results to a new layer in geopackage
    samplePointsData_withoutNan.to_file(
        gpkgPath,
        layer=config["parameters"]["samplepointResult"],
        driver='GPKG')

    endTime = time.time() - startTime
    print('Total time is : {0:.2f} hours or {1:.2f} seconds'.format(
        endTime / 3600, endTime))
