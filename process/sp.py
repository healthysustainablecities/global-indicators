################################################################################
# Script: sp.py
# Description: This script is for preparing all the fields for sample points
# All the cities should run this script first to get the pre-prepared sample points
# before running the aggregation.

# Two major outputs:
# 1. average poplulation and intersection density per sample sample point
# 2. accessibility, dailyliving and walkability score per sample point

import os
import sys
import time
from tqdm import tqdm
import networkx as nx
import fiona
import geopandas as gpd
import numpy as np
import pandas as pd

import osmnx as ox
import setup_sp as ssp

if __name__ == "__main__":
    # use the script from command line, change directory to '/process' folder
    # then 'python sp.py [city]' to process city-specific idnicators
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
    
    # geopackage path where to read all the required layers
    gpkgPath = os.path.join(dirname, config["folder"], config["geopackagePath"])   
    
    # define original graphml filepath
    ori_graphml_filepath = os.path.join(dirname, config["folder"], config["graphmlName"])
    
    if not os.path.exists(gpkgPath):
        # check if these files are located in the study region folder (ie. output location for pre-processing)
        alt_dir = f"./data/study_region/{config['study_region_full']}"
        alt_sources = (f"{alt_dir}/{os.path.basename(gpkgPath)}",
                       f"{alt_dir}/{os.path.basename(ori_graphml_filepath)}")
        if sum([os.path.exists(x) for x in alt_sources])==2:
            gpkgPath,ori_graphml_filepath = alt_sources
        else:
            sys.exit(f"\nThe required input files ({os.path.basename(gpkgPath)} and {os.path.basename(gpkgPath)}) do not appear to exist in either the ./data/input folder or {alt_dir} folder.  "
             "Please ensure both of these file exist in one of these locations, or that the input configuration is correctly re-parameterised to recognise an alternative location.")
    
    # geopackage path where to save processing layers
    gpkgPath_output = os.path.join(dirname, config["folder"], config["geopackagePath_output"])
    
    # Check if geopackage has a -wal file associated with it
    # if so it is likely open and locked for use by another software package (e.g. QGIS)
    # and will be unable to be used
    for required_gpkg in [gpkgPath,gpkgPath_output]:
        if os.path.exists(f'{required_gpkg}-wal'):
            sys.exit(
            f"\nIt appears that the required geopackage {required_gpkg} may be open in another software package, " 
            "due to the presence of a Write Ahead Logging (WAL) file associated with it.  Please ensure that the input "  
            "geopackage is not being used in any other software before continuing, and that the file "
           f"'{required_gpkg}-wal' is not present before continuing."
           )
    
    # read projected graphml filepath
    proj_graphml_filepath = os.path.join(dirname, config["folder"], config["graphmlProj_name"])
    
    G_proj = ssp.read_proj_graphml(proj_graphml_filepath,
                                   ori_graphml_filepath, 
                                   config["to_crs"],
                                   undirected=True,
                                   retain_fields=['osmid','length'])
    
    # copy input geopackage to output geopackage, if not already exist
    input_layers = fiona.listlayers(gpkgPath)
    if not os.path.isfile(gpkgPath_output):
        print("Initialise sample point output geopackage as a copy of input geopackage")
        os.system(f'cp {gpkgPath} {gpkgPath_output}')
        output_layers = input_layers
    else:
        output_layers = fiona.listlayers(gpkgPath_output)
        print("Sample point geopackage exists.")
        for layer in [x for x in input_layers if x not in output_layers]:
            print(f" - updating output geopackage to contain the layer '{layer}'")
            gpkgPath_input = gpd.read_file(gpkgPath, layer=layer)
            gpkgPath_input.to_file(gpkgPath_output, layer=layer, driver="GPKG")
    
    # read hexagon layer of the city from disk, the hexagon layer is 250m*250m
    # it should contain population estimates and intersection information
    hexes = gpd.read_file(gpkgPath_output, layer=parameters["hex250"])
    hexes.set_index('index',inplace=True)
    
    print("\nFirst pass node-level neighbourhood analysis (Calculate average population and intersection density for each intersection node in study regions, taking mean values from distinct hexes within neighbourhood buffer distance)")
    nh_startTime = time.time()
    population_density = parameters["population_density"]
    intersection_density = parameters["intersection_density"]
    nh_fields_points = [population_density,intersection_density]
    # read from disk if exist
    if 'nodes_pop_intersect_density' in output_layers:                        
        print("  - Read poplulation and intersection density from local file.")
        gdf_nodes_simple = gpd.read_file(gpkgPath_output, layer='nodes_pop_intersect_density')
        gdf_nodes_simple.set_index('osmid', inplace=True)
    else:
        print("  - Set up simple nodes")
        gdf_nodes = ox.graph_to_gdfs(G_proj, nodes=True, edges=False)
        gdf_nodes.osmid = gdf_nodes.osmid.astype(int)
        gdf_nodes = gdf_nodes.drop_duplicates(subset="osmid")
        gdf_nodes.set_index('osmid', inplace=True)
        # associate nodes with hex_id
        gdf_nodes = ssp.spatial_join_index_to_gdf(gdf_nodes, hexes, right_index_name='hex_id',join_type='within')
        # keep only the unique node id column
        gdf_nodes = gdf_nodes[["hex_id","geometry"]]
        # drop any nodes which are na (they are outside the buffered study region and not of interest)
        gdf_nodes_simple = gdf_nodes[~gdf_nodes.hex_id.isna()].copy()
        gdf_nodes = gdf_nodes[["hex_id"]]
        
    if len([x for x in nh_fields_points if x not in gdf_nodes_simple.columns]) > 0:
        # Calculate average poplulation and intersection density for each intersection node in study regions
        # taking mean values from distinct hexes within neighbourhood buffer distance
        nh_fields_hex = ['pop_per_sqkm','intersections_per_sqkm']   
        # Create a dictionary of edge index and integer values of length
        # The length attribute was saved as string, so must be recast to use as weight
        # The units are meters, so the decimal precision is unnecessary (error is larger than this; meter is adequate)
        weight = dict(zip([k for k in G_proj.edges],[int(float(G_proj.edges[k]['length'])) for k in G_proj.edges]))
        
        # Add a new edge attribute using the integer weights
        nx.set_edge_attributes(G_proj, weight, 'weight')
        
        # run all pairs analysis
        total_nodes = len(gdf_nodes_simple)
        nh_distance = parameters["neighbourhood_distance"]
        print(f'  - Generate {nh_distance}m  neighbourhoods for nodes (All pairs Dijkstra shortest path analysis)')
        all_pairs_d = pd.DataFrame([(k,v.keys()) for k,v in tqdm(nx.all_pairs_dijkstra_path_length(G_proj,1000,'weight'),
                                            total=total_nodes,unit='nodes',desc=' '*18)],
                      columns = ['osmid','nodes']).set_index('osmid')
        # extract results
        print('  - Summarise attributes (average value from unique associated hexes within nh buffer distance)...')

        result = pd.DataFrame([tuple(hexes.loc[gdf_nodes.loc[all_pairs_d.loc[n].nodes,'hex_id'].dropna().unique(),    
                                        nh_fields_hex].mean().values) for index,n in    
                                            tqdm(np.ndenumerate(gdf_nodes_simple.index.values),total=total_nodes,desc=' '*18)],
                         columns = nh_fields_points,
                         index=gdf_nodes_simple.index.values)
        gdf_nodes_simple = gdf_nodes_simple.join(result)
        
        # save in geopackage (so output files are all kept together)
        gdf_nodes_simple.to_file(gpkgPath_output, layer='nodes_pop_intersect_density', driver="GPKG")
    
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
    unnecessary_columns = [x for x in 
                             ["geometry", "id", "lat", "lon", "y", "x", "highway", "ref"] 
                                if x in gdf_nodes_poi_dist.columns]
    gdf_nodes_poi_dist.drop(unnecessary_columns,axis=1, inplace=True, errors="ignore")
    
    # replace -999 values (meaning no destination reached in less than 500 metres) as nan
    gdf_nodes_poi_dist = round(gdf_nodes_poi_dist, 0).replace(-999, np.nan).astype("Int64")
    
    # read sample points from disk (in city-specific geopackage)
    samplePointsData = gpd.read_file(gpkgPath_output, layer=parameters["samplePoints"])
        
    # create 'hex_id' for sample point, if it not exists
    if "hex_id" not in samplePointsData.columns:
        samplePointsData = ssp.spatial_join_index_to_gdf(samplePointsData, hexes, right_index_name='hex_id',join_type='within')
    
    print("Restrict sample points to those not located in hexagons with a population below "
          f"the minimum threshold value ({parameters['pop_min_threshold']})")
    below_minimum_pop_hex_ids = list(hexes.query(f'pop_est < {parameters["pop_min_threshold"]}').index.values)
    samplePointsData = samplePointsData[~samplePointsData.hex_id.isin(below_minimum_pop_hex_ids)]
    
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
    samplePointsData[binary_names] = (samplePointsData[distance_names] <= parameters['accessibility_distance']) \
                                           .astype("Int64").fillna(0)
    
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
                samplePointsData[var] =  ((samplePointsData[columns] -  samplePointsData[columns].mean()) \
                                                 / samplePointsData[columns].std()).sum(axis=1)       
    
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
