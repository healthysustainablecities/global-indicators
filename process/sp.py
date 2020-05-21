################################################################################
# Script: sp.py
# Description: This script is for preparing all the fields for sample points
# All the cities should run this script first to get the pre-prepared sample points
# before running the aggregation.

# Two major outputs:
# 1. average poplulation and intersection density per sample sample point
# 2. accessibility, dailyliving and walkability score per sample point

# notice: must close the geopackage connection in QGIS.Otherwise, an error occurred when reading
################################################################################
import geopandas as gpd
import pandas as pd
import osmnx as ox
import numpy as np
import os
import setup_sp as ssp
import setup_config as sc # import project config parameters
import time
from multiprocessing import Pool, cpu_count, Value, Manager, Process
from functools import partial
import json
import fiona
import sys

if __name__ == '__main__':
    # use the script from command line, change directory to '/process' folder
    # then 'python sp.py odense.json' to process city-specific idnicators
    startTime = time.time()

    # get the work directory
    dirname = os.path.abspath('')

    # the configuration file should put in the '/configuration' folder located at the same folder as scripts
    # load city-specific configeration file
    jsonFile = 'configuration/' + sys.argv[1]
    jsonPath = os.path.join(dirname, jsonFile)
    try:
        with open(jsonPath) as json_file:
            config = json.load(json_file)
    except Exception as e:
        print('Failed to read json file.')
        print(e)

    # output the processing city name to users
    print('Process city: {}'.format(config['study_region']))

    # read projected graphml filepath
    graphmlProj_path = os.path.join(dirname, config['folder'],
                                        config['graphmlProj_name'])

    # define original graphml filepath
    graphml_path = os.path.join(dirname, config['folder'],
                                config['graphmlName'])

    G_proj = ssp.read_proj_graphml(graphmlProj_path, graphml_path, config['to_crs'])

    # geopackage path where to read all the required layers
    gpkgPath = os.path.join(dirname, config['folder'],
                            config['geopackagePath'])

    # geopackage path where to save processing layers
    gpkgPath_output = os.path.join(dirname, config['folder'],config['geopackagePath_output'])

    # copy input geopackage to output geopackage, if not already exist
    if not os.path.isfile(gpkgPath_output):
        print('Create study region sample point output file')
        for layer in fiona.listlayers(gpkgPath):
            gpkgPath_input = gpd.read_file(gpkgPath, layer=layer)
            gpkgPath_input.to_file(gpkgPath_output, layer=layer, driver='GPKG')
    else:
        print('Study region sample point output file exists')

    # read hexagon layer of the city from disk, the hexagon layer is 250m*250m
    # it should contain population estimates and intersection information
    hex250 = gpd.read_file(gpkgPath_output, layer=sc.parameters['hex250'])

    # get nodes from the city projected graphml
    gdf_nodes = ox.graph_to_gdfs(G_proj, nodes=True, edges=False)
    gdf_nodes.osmid = gdf_nodes.osmid.astype(int)
    gdf_nodes = gdf_nodes.drop_duplicates(subset='osmid')
    # keep only the unique node id column
    gdf_nodes_simple = gdf_nodes[['osmid']].copy()
    del gdf_nodes

    # calculate average poplulation and intersection density for each sample point in study regions
    # the steps are as follows:
        # 1. use the OSM pedestrain network (graphml in disk) to calculate local 1600m neighborhood per urban sample points (in disk)
        # 2. load 250m hex grid from disk with population and network intersections density data
        # 3. then intersect 1600m sample point neighborhood with 250m hex grid
        # to associate pop and intersections density data with sample points by averaging the hex-level density
        # final result is urban sample point dataframe with osmid, pop density, and intersection density

    # read from disk if exist
    if os.path.isfile(os.path.join(dirname, config['folder'],
                         config['tempCSV'])):
        print('Read poplulation and intersection density from local file.')
        gdf_nodes_simple = pd.read_csv(os.path.join(dirname, config['folder'],
                         config['tempCSV']))

    # otherwise,calculate using single thred or multiprocessing
    else:
        print('Calculate average poplulation and intersection density.')

        # read search distance from json file, the default should be 1600m
        # the search distance is used to defined the radius of a sample point as a local neighborhood
        distance = sc.parameters['search_distance']

        # read pop density and intersection density filed names from the  city-specific configeration file
        pop_density = sc.samplePoint_fieldNames[
            'sp_local_nh_avg_pop_density']
        intersection_density = sc.samplePoint_fieldNames[
            'sp_local_nh_avg_intersection_density']

        # get the nodes GeoDataFrame row length for use in later iteration
        rows = gdf_nodes_simple.shape[0]

        # if provide 'true' in command line, then using multiprocessing, otherwise, using single thread
        # Notice: Meloubrne has the largest number of sample points, which needs 13 GB memory for docker using 3 cpus.
        if len(sys.argv) > 2:
            if sys.argv[2].lower() == 'true':
                # method1: new way to use multiprocessing

                # get a list of nodes id for later iteration purpose
                node_list = gdf_nodes_simple.osmid.tolist()
                node_list.sort()
                pool = Pool(cpu_count())
                result_objects = pool.starmap_async(
                    ssp.calc_sp_pop_intect_density_multi,
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
                ssp.calc_sp_pop_intect_density,
                args=(G_proj, hex250, pop_density, intersection_density, distance,
                      val, rows))
            # Concatenate the average of population and intersections back to the df of sample points
            gdf_nodes_simple = pd.concat([gdf_nodes_simple, df_result], axis=1)

        # save the pop and intersection density to a CSV file
        gdf_nodes_simple.to_csv(
                os.path.join(dirname, config['folder'],
                             config['tempCSV']))

    # set osmid as index
    gdf_nodes_simple.set_index('osmid', inplace=True, drop=False)
    print('The time to finish average pop and intersection density is: {}'.
              format(time.time() - startTime))

    # read sample points from disk (in city-specific geopackage)
    samplePointsData = gpd.read_file(
        gpkgPath_output, layer=sc.parameters['samplePoints'])

    # create 'hex_id' for sample point, if it not exists
    if 'hex_id' not in samplePointsData.columns.tolist():
        samplePointsData = ssp.createHexid(samplePointsData, hex250)

    # Calculate accessibility to POI (supermarket,convenience,pt,pso) and walkability for sample points
    # steps as follow:
        # 1. using pandana packadge to calculate distance to access from sample points to destinations (daily living destinations, public open space)
        # 2. calculate accessibiity score per sample point: transform accessibility distance to binary measure: 1 if access <= 500m, 0 otherwise
        # 3. calculate daily living score by summing the accessibiity scores to all POIs (excluding pos)
        # 4. calculate walkability score per sample point: get zscores for daily living accessibility, populaiton density and intersections pop_density; sum these three zscores at sample point level

    print('Calculate assessbility to POIs.')

    # create the pandana network, use network nodes and edges
    gdf_nodes, gdf_edges = ox.graph_to_gdfs(G_proj)
    net = ssp.create_pdna_net(gdf_nodes, gdf_edges)

    # read 'daily living destinations' point layer (supermarket,convenience,pt) from disk
    gdf_poi1 = gpd.read_file(gpkgPath_output,
                             layer=sc.parameters['destinations'])

    # read field names from json file
    poi_names = [
        sc.parameters['supermarket'],
        sc.parameters['convenience'], sc.parameters['PT']
    ]

    # read accessibility distance from configuration file, which is 500m
    distance = sc.parameters['accessibility_distance']

    # read output field names from json file
    output_fieldNames1 = [
        sc.samplePoint_fieldNames['sp_nearest_node_supermarket_dist'],
        sc.samplePoint_fieldNames['sp_nearest_node_convenience_dist'],
        sc.samplePoint_fieldNames['sp_nearest_node_pt_dist']
    ]

    # zip the input and output field names
    names1 = list(zip(poi_names, output_fieldNames1))

    # calculate the distance from each node to POI
    gdf_poi_dist1 = ssp.cal_dist_node_to_nearest_pois(gdf_poi1, distance, net, *(names1))

    # read open space 'aos_nodes_30m_line' layer from geopackage
    gdf_poi2 = gpd.read_file(gpkgPath_output, layer=sc.parameters['pos'])

    # read field names from json file
    names2 = [(sc.parameters['pos'],
               sc.samplePoint_fieldNames['sp_nearest_node_pos_dist'])]

    # calculate the distance from each node to public open space,
    # filterattr=False to indicate the layer is 'aos_nodes_30m_line'
    gdf_poi_dist2 = ssp.cal_dist_node_to_nearest_pois(gdf_poi2,
                                     distance,
                                     net,
                                     *names2,
                                     filterattr=False)

    # concatenate two dataframes into one
    gdf_nodes_poi_dist = pd.concat([gdf_nodes, gdf_poi_dist1, gdf_poi_dist2],
                                   axis=1)

    # convert distance of each nodes to binary index
    output_fieldNames1.append(
        sc.samplePoint_fieldNames['sp_nearest_node_pos_dist'])
    output_fieldNames2 = [
        sc.samplePoint_fieldNames['sp_nearest_node_supermarket_binary'],
        sc.samplePoint_fieldNames['sp_nearest_node_convenience_binary'],
        sc.samplePoint_fieldNames['sp_nearest_node_pt_binary'],
        sc.samplePoint_fieldNames['sp_nearest_node_pos_binary']
    ]
    names3 = list(zip(output_fieldNames1, output_fieldNames2))
    gdf_nodes_poi_dist = ssp.convert_dist_to_binary(gdf_nodes_poi_dist, *names3)

    # set index of gdf_nodes_poi_dist, using 'osmid' as the index
    gdf_nodes_poi_dist.set_index('osmid', inplace=True, drop=False)

    # drop unuseful columns
    gdf_nodes_poi_dist.drop(
        ['geometry', 'id', 'lat', 'lon', 'y', 'x', 'highway', 'ref'],
        axis=1,
        inplace=True)

    # for each sample point, create a new field to save the osmid of the closest nodes,
    # which is used for joining to nodes
    samplePointsData['closest_node_id'] = np.where(
        samplePointsData.n1_distance <= samplePointsData.n2_distance,
        samplePointsData.n1, samplePointsData.n2)

    # join the two tables (sample point pop and intersection density + node to POIs accessibility distance)
    # based on node id (link sample points to nearest nodes)
    samplePointsData['closest_node_id'] = samplePointsData[
        'closest_node_id'].astype(int)

    # first, join accessibility to POIs results from nodes to sample points based on node id
    samplePointsData = samplePointsData.join(gdf_nodes_poi_dist,
                                             on='closest_node_id',
                                             how='left',
                                             rsuffix='_nodes1')

    # second, join pop and intersection density from nodes to sample points based on node id
    samplePointsData = samplePointsData.join(gdf_nodes_simple,
                                             on='closest_node_id',
                                             how='left',
                                             rsuffix='_nodes2')

    # drop the nan rows samplePointsData, and deep copy to a new variable
    samplePointsData_withoutNan = samplePointsData.dropna().copy()
    nanData = samplePointsData[~samplePointsData.index.
                               isin(samplePointsData_withoutNan.index)]

    # save the nan rows to a new layer in geopackage, in case someone will check it
    nanData.to_file(gpkgPath_output,
                    layer=sc.parameters['dropNan'],
                    driver='GPKG')
    del nanData

    # create new field for daily living score, and exclude public open space
    output_fieldNames2.pop()
    samplePointsData_withoutNan[
        'sp_daily_living_score'] = samplePointsData_withoutNan[
            output_fieldNames2].sum(axis=1)

    oriFieldNames = [
        sc.samplePoint_fieldNames['sp_local_nh_avg_pop_density'],
        sc.samplePoint_fieldNames['sp_local_nh_avg_intersection_density'],
        sc.samplePoint_fieldNames['sp_daily_living_score']
    ]
    newFieldNames = [
        sc.samplePoint_fieldNames['sp_zscore_local_nh_avgpopdensity'],
        sc.samplePoint_fieldNames['sp_zscore_local_nh_avgintdensity'],
        sc.samplePoint_fieldNames['sp_zscore_daily_living_score']
    ]

    # calculate zscore for walkability components
    samplePointsData_withoutNan = ssp.cal_zscores(samplePointsData_withoutNan,
                                                  oriFieldNames, newFieldNames)

    # sum these three zscores for walkability index
    samplePointsData_withoutNan[
        'sp_walkability_index'] = samplePointsData_withoutNan[
            newFieldNames].sum(axis=1)

    # save the sample points with all the desired results to a new layer in geopackage
    samplePointsData_withoutNan.to_file(
        gpkgPath_output,
        layer=sc.parameters['samplepointResult'],
        driver='GPKG')

    endTime = time.time() - startTime
    print('Total time is : {0:.2f} hours or {1:.2f} seconds'.format(
        endTime / 3600, endTime))
