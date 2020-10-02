################################################################################
# Script: sp.py
# Description: This script is for preparing all the fields for sample points
# All the cities should run this script first to get the pre-prepared sample points
# before running the aggregation.

# Two major outputs:
# 1. average poplulation and intersection density per sample sample point
# 2. accessibility, dailyliving and walkability score per sample point

import json
import os
import sys
import time
from multiprocessing import Pool, Value, cpu_count

import fiona

# notice: must close the geopackage connection in QGIS.Otherwise, an error occurred when reading
################################################################################
import geopandas as gpd
import numpy as np
import pandas as pd

import osmnx as ox
import setup_sp as ssp

if __name__ == "__main__":
    # use the script from command line, change directory to '/process' folder
    # then 'python sp.py odense.json' to process city-specific idnicators
    startTime = time.time()
    today = time.strftime("%Y-%m-%d")
    # get the work directory
    dirname = os.path.abspath("")
    
    assumptions = """
    This code assumes the name of a known city to be passed as an argument, however none was provided.
    
    Configuration python files containing the dictionaries 'config' and 'parameters' are written
    to the ./configuration directory for cities through use of the set up configuration script setup_config.py,
    like so: 
    python setup_config.py auckland
    
    or, to generate set up scripts for all cities
    python setup_config.py
    """
    
    # load city-specific configuration file
    if len(sys.argv) < 2:
        print(assumptions)
        sys.exit()
    
    city = sys.argv[1]
    configuration_file = f'{dirname}/configuration/{city}.py'
    try:
        exec(open(configuration_file).read())
    except Exception as e:
        print(f"Failed to read configuration file {configuration_file}.\n\n{assumptions}")
        print(e)
    
    # output the processing city name to users
    print(f"\nGlobal indicators project {today}\n\nProcess city: {config['study_region'].title()}\n")
    
    # read projected graphml filepath
    proj_graphml_filepath = os.path.join(dirname, config["folder"], config["graphmlProj_name"])
    
    # define original graphml filepath
    ori_graphml_filepath = os.path.join(dirname, config["folder"], config["graphmlName"])
    
    G_proj = ssp.read_proj_graphml(proj_graphml_filepath, ori_graphml_filepath, config["to_crs"])
    
    # geopackage path where to read all the required layers
    gpkgPath = os.path.join(dirname, config["folder"], config["geopackagePath"])
    
    # geopackage path where to save processing layers
    gpkgPath_output = os.path.join(dirname, config["folder"], config["geopackagePath_output"])
    
    # copy input geopackage to output geopackage, if not already exist
    if not os.path.isfile(gpkgPath_output):
        print("Create study region sample point output file")
        for layer in fiona.listlayers(gpkgPath):
            gpkgPath_input = gpd.read_file(gpkgPath, layer=layer)
            gpkgPath_input.to_file(gpkgPath_output, layer=layer, driver="GPKG")
    else:
        print("Study region sample point output file exists")
    
    # read hexagon layer of the city from disk, the hexagon layer is 250m*250m
    # it should contain population estimates and intersection information
    hexes = gpd.read_file(gpkgPath_output, layer=parameters["hex250"])
    
    # get nodes from the city projected graphml
    gdf_nodes = ox.graph_to_gdfs(G_proj, nodes=True, edges=False)
    gdf_nodes.osmid = gdf_nodes.osmid.astype(int)
    gdf_nodes = gdf_nodes.drop_duplicates(subset="osmid")
    # keep only the unique node id column
    gdf_nodes_simple = gdf_nodes[["osmid"]].copy()
    del gdf_nodes
    
    # calculate average poplulation and intersection density for each sample point in study regions
    # the steps are as follows:
    # 1. use the OSM pedestrain network (graphml in disk) to calculate local 1600m neighborhood per urban
    #    sample points (in disk)
    # 2. load 250m hex grid from disk with population and network intersections density data
    # 3. then intersect 1600m sample point neighborhood with 250m hex grid
    # to associate pop and intersections density data with sample points by averaging the hex-level density
    # final result is urban sample point dataframe with osmid, pop density, and intersection density
    # read pop density and intersection density filed names from the  city-specific configeration file
    population_density = parameters["population_density"]
    intersection_density = parameters["intersection_density"]
    
    # read from disk if exist
    nh_startTime = time.time()
    if os.path.isfile(os.path.join(dirname, config["folder"], config["tempCSV"])):
        print("Read poplulation and intersection density from local file.")
        gdf_nodes_simple = pd.read_csv(os.path.join(dirname, config["folder"], config["tempCSV"]))
    # otherwise,calculate using single thred or multiprocessing
    else:
        print("\nCalculate local walkable neighbourhood statistics")
        # Graph for Walkability analysis should not be directed
        # (ie. it is assumed pedestrians are not influenced by one way streets)
        # note that when you save the undirected G_proj feature, if you re-open it, it is directed again
        #
        # >>> G_proj = ox.load_graphml(proj_graphml_filepath)
        # >>> nx.is_directed(G_proj)
        # True
        # >>> G_proj = ox.get_undirected(G_proj)
        # >>> nx.is_directed(G_proj)
        # False
        # >>> ox.save_graphml(G_proj, proj_graphml_filepath)
        # >>> G_proj = ox.load_graphml(proj_graphml_filepath)
        # >>> nx.is_directed(G_proj)
        # True
        # so no point undirecting it before saving - you have to undirect again regardless
        G_proj = ox.get_undirected(G_proj)
        
        # read search distance from json file, the default should be 1600m
        # the search distance is used to defined the radius of a sample point as a local neighborhood
        neighbourhood_distance = parameters["neighbourhood_distance"]
        
        # get the nodes GeoDataFrame row length for use in later iteration
        rows = gdf_nodes_simple.shape[0]
        
        # if provide 'true' in command line, then using multiprocessing, otherwise, using single thread
        # Notice: Meloubrne has the largest number of sample points, which needs 13 GB memory for docker using 3 cpus.
        if len(sys.argv) > 2:
            if sys.argv[2].lower() == "true":
                # method1: new way to use multiprocessing
                
                # get a list of nodes id for later iteration purpose
                node_list = gdf_nodes_simple.osmid.tolist()
                node_list.sort()
                
                try:
                    # load the resources config to see how many CPUs to use
                    with open('./configuration/resources.json') as f:
                        resources = json.load(f)
                    cpus = resources['cpus']
                    assert cpus > 0 and cpus <= cpu_count()
                except Exception:
                    # if any exception or cpus<=0, use all available CPUs
                    cpus = cpu_count()
                
                print('Using {} CPUs'.format(cpus))
                pool = Pool(cpus)
                result_objects = pool.starmap_async(
                    ssp.calc_sp_pop_intect_density_multi,
                    [(G_proj, hexes, neighbourhood_distance, rows, node, index) for index, node in enumerate(node_list)],
                    chunksize=1000,
                ).get()
                pool.close()
                pool.join()
                gdf_nodes_simple = pd.DataFrame(result_objects, columns=["osmid", population_density, intersection_density])
        
        else:
            # method 2: single thread, use pandas apply()
            # create counter for loop
            val = Value("i", 0)
            df_result = gdf_nodes_simple["osmid"].apply(
                ssp.calc_sp_pop_intect_density,
                args=(G_proj, hexes, population_density, intersection_density, neighbourhood_distance, val, rows),
            )
            # Concatenate the average of population and intersections back to the df of sample points
            gdf_nodes_simple = pd.concat([gdf_nodes_simple, df_result], axis=1)
        
        # save the pop and intersection density to a CSV file
        gdf_nodes_simple.to_csv(os.path.join(dirname, config["folder"], config["tempCSV"]))
    
    print(f"Time taken to calculate or load city local neighbourhood statistics: {(time.time() - nh_startTime)/60:02g} mins")
    
    # Calculate accessibility to POI (fresh_food_market,convenience,pt,pso) and
    # walkability for sample points steps as follow:
    # 1. using pandana packadge to calculate distance to access from sample
    #    points to destinations (daily living destinations, public open space)
    # 2. calculate accessibiity score per sample point: transform accessibility
    #    distance to binary measure: 1 if access <= 500m, 0 otherwise
    # 3. calculate daily living score by summing the accessibiity scores to all
    #    POIs (excluding pos)
    # 4. calculate walkability score per sample point: get zscores for daily
    #    living accessibility, populaiton density and intersections population_density;
    #    sum these three zscores at sample point level
    
    print("\nCalculate assessbility to POIs.")
    # set osmid as index
    gdf_nodes_simple.set_index("osmid", inplace=True, drop=False)
    # read accessibility distance from configuration file, which is 500m
    
    # create the pandana network, use network nodes and edges
    gdf_nodes, gdf_edges = ox.graph_to_gdfs(G_proj)
    network = ssp.create_pdna_net(gdf_nodes, gdf_edges, predistance=parameters["accessibility_distance"])
    
    distance_results = {}
    print("\nCalculating nearest node analyses ...")
    for analysis_key in config['nearest_node_analyses']:
        print(f'\n\t- {analysis_key}')
        analysis = config['nearest_node_analyses'][analysis_key]
        layer_analysis_count = len(analysis['layers'])
        for layer in analysis['layers']:
            if layer is not None:
                output_names = analysis['output_names'].copy()
                if layer_analysis_count > 1 and layer_analysis_count==len(analysis['output_names']):
                    # assume that output names correspond to layers, and refresh per analysis
                    output_names = [output_names[analysis['layers'].index(layer)]]
                
                print(f'\t\t{output_names}')
                gdf_poi = gpd.read_file(f"data/{analysis['geopackage']}", layer = layer) 
                distance_results[f'{analysis}_{layer}'] = ssp.cal_dist_node_to_nearest_pois(gdf_poi, 
                                                             parameters["accessibility_distance"], 
                                                             network, 
                                                             category_field = analysis['category_field'],
                                                             categories = analysis['categories'],
                                                             filter_field = analysis['filter_field'],
                                                             filter_iterations = analysis['filter_iterations'],
                                                             output_names = output_names,
                                                             output_prefix = 'sp_nearest_node_')
            else:
                # create null results --- e.g. for GTFS analyses where no layer exists
                distance_results[f'{analysis_key}_{layer}'] = pd.DataFrame(index=gdf_nodes.index, 
                                                                columns=[f'sp_nearest_node_{x}' for x in analysis['output_names']])
    
    # concatenate analysis dataframes into one
    gdf_nodes_poi_dist = pd.concat([gdf_nodes]+[distance_results[x] for x in distance_results], axis=1)
    
    # set index of gdf_nodes_poi_dist, using 'osmid' as the index, and remove other unnecessary columns
    gdf_nodes_poi_dist.set_index("osmid",inplace=True)
    unnecessary_columns = [x for x in ["geometry", "id", "lat", "lon", "y", "x", "highway", "ref"] if x in gdf_nodes_poi_dist.columns]
    gdf_nodes_poi_dist.drop(unnecessary_columns,axis=1, inplace=True, errors="ignore")
    
    # replace -999 values (meaning no destination reached in less than 500 metres) as nan
    gdf_nodes_poi_dist = round(gdf_nodes_poi_dist, 0).replace(-999, np.nan).astype("Int64")
    
    # read sample points from disk (in city-specific geopackage)
    samplePointsData = gpd.read_file(gpkgPath_output, layer=parameters["samplePoints"])
    
    # create 'hex_id' for sample point, if it not exists
    if "hex_id" not in samplePointsData.columns.tolist():
        samplePointsData = ssp.createHexid(samplePointsData, hexes)
    
    samplePointsData.set_index("point_id", inplace=True)
    
    distance_names = list(gdf_nodes_poi_dist.columns)
    
    # Estimate full distance to destinations for sample points
    full_nodes = ssp.create_full_nodes(
        samplePointsData,
        gdf_nodes_simple,
        gdf_nodes_poi_dist,
        distance_names,
        population_density,
        intersection_density,
    )
        
    samplePointsData = samplePointsData[["hex_id", "edge_ogc_fid", "geometry"]].join(full_nodes, how="left")
    
    # create binary distances evaluated against accessibility distance
    binary_names = [f"{x.replace('nearest_node','access')}_binary" for x in distance_names]
    samplePointsData[binary_names] = (samplePointsData[distance_names] <= parameters['accessibility_distance']).astype("Int64").fillna(0)
    
    print("Calculating sample point specific analyses ...")
    # Defined in generated config file, e.g. daily living score, walkability index, etc
    for analysis in config['sample_point_analyses']:
        print(f"\t - {analysis}")
        for var in config['sample_point_analyses'][analysis]:
            columns = config['sample_point_analyses'][analysis][var]['columns']
            formula = config['sample_point_analyses'][analysis][var]['formula']
            axis    = config['sample_point_analyses'][analysis][var]['axis']
            if formula == "sum":
                samplePointsData[var] = samplePointsData[columns].sum(axis=axis)
            if formula == "max":
                samplePointsData[var] = samplePointsData[columns].max(axis=axis)
            if formula == "sum_of_z_scores":
                samplePointsData[var] =  ((samplePointsData[columns] -  samplePointsData[columns].mean())/ samplePointsData[columns].std()).sum(axis=1)       
    
    # hex_id and edge_ogc_fid are integers
    samplePointsData[samplePointsData.columns[0:2]] = samplePointsData[samplePointsData.columns[0:2]].astype(int)
    # remaining non-geometry fields are float
    samplePointsData[samplePointsData.columns[3:]] = samplePointsData[samplePointsData.columns[3:]].astype(float)
    print("Save to geopackage...")
    # save the sample points with all the desired results to a new layer in geopackage
    samplePointsData = samplePointsData.reset_index()
    samplePointsData.to_file(gpkgPath_output, layer=parameters["samplepointResult"], driver="GPKG")

    endTime = time.time() - startTime
    print("Total time is : {:.2f} minutes".format(endTime / 60))
