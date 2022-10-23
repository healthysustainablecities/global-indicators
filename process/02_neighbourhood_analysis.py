################################################################################
# Script: 02_neighbourhood_analysis.py
# Description: 
# This script creates neighbourhood indicators for sample points.  
# To run it, supply a study region code name.  The list of configured codenames is displayed 
# if run with no region name as an argument.
# It is  to be run after 01_study_region_setup.py, which collates and processes the required data.
# Once run, the sample points may be aggregated to a neighbourhood small area grid and for overall
# city summaries by running 03_aggregation.py.

# As a result of running the script, a layer is added to the study region's geopackage file
# containing sample point indicators ("samplePointsData").  These indicators include:
# 1. average population and intersection density per sample sample point
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
from pre_process.setup_sp import read_proj_graphml,spatial_join_index_to_gdf, create_pdna_net, cal_dist_node_to_nearest_pois, spatial_join_index_to_gdf, create_full_nodes, binary_access_score

# Set up project and region parameters for GHSCIC analyses
from pre_process._project_setup import *

def main():
    startTime = time.time()
    
    for file in [gpkg,graphml]:
        if not os.path.exists(file):
            sys.exit(f"\n\nSpatial features required for analysis of this city ({file}) weren't able to be located; please confirm that the study region setup scripts have been successfully completed and that this file exists for this study region in the specified path.\n\n")
    
    # Check if geopackage has a -wal file associated with it
    # if so it is likely open and locked for use by another software package (e.g. QGIS)
    # and will be unable to be used
    if os.path.exists(f'{gpkg}-wal'):
        sys.exit(
        f"\nIt appears that the required geopackage {gpkg} may be open in another software package, "
        "due to the presence of a Write Ahead Logging (WAL) file associated with it.  Please ensure that the input "
        "geopackage is not being used in any other software before continuing, and that the file "
       f"'{gpkg}-wal' is not present before continuing."
       )
    
    input_layers = fiona.listlayers(gpkg)
    G_proj = read_proj_graphml(
        graphml_proj,
        graphml,
        srid,
        undirected=True,
        retain_fields=['osmid','length'])
    
    grid = gpd.read_file(gpkg, layer=population_grid)
    grid.set_index('grid_id',inplace=True)
    
    print("\nFirst pass node-level neighbourhood analysis (Calculate average population and intersection density "
          "for each intersection node in study regions, taking mean values from distinct grid cells within "
          "neighbourhood buffer distance)")
    nh_startTime = time.time()
    # read from disk if exist
    if 'nodes_pop_intersect_density' in input_layers:
        print("  - Read population and intersection density from local file.")
        gdf_nodes_simple = gpd.read_file(gpkg, layer='nodes_pop_intersect_density')
        gdf_nodes_simple.set_index('osmid', inplace=True)
    else:
        print("  - Set up simple nodes")
        gdf_nodes = ox.graph_to_gdfs(G_proj, nodes=True, edges=False)
        gdf_nodes.osmid = gdf_nodes.osmid.astype(int)
        gdf_nodes = gdf_nodes.drop_duplicates(subset="osmid")
        gdf_nodes.set_index('osmid', inplace=True)
        # associate nodes with id
        gdf_nodes = spatial_join_index_to_gdf(
            gdf_nodes, 
            grid, 
            right_index_name='grid_id',
            join_type='within'
            )
        # keep only the unique node id column
        gdf_nodes = gdf_nodes[["grid_id","geometry"]]
        # drop any nodes which are na 
        # (they are outside the buffered study region and not of interest)
        gdf_nodes_simple = gdf_nodes[~gdf_nodes.grid_id.isna()].copy()
        gdf_nodes = gdf_nodes[["grid_id"]]
    if len([x for x in [population_density,intersection_density] if x not in gdf_nodes_simple.columns]) > 0:
        # Calculate average population and intersection density for each intersection node in study regions
        # taking mean values from distinct grid cells within neighbourhood buffer distance
        nh_grid_fields = ['pop_per_sqkm','intersections_per_sqkm']
        # Create a dictionary of edge index and integer values of length
        # The length attribute was saved as string, so must be recast to use as weight
        # The units are meters, so the decimal precision is unnecessary (error is larger than this; meter is adequate)
        weight = dict(
            zip([k for k in G_proj.edges],
                [int(float(G_proj.edges[k]['length'])) for k in G_proj.edges])
            )
        # Add a new edge attribute using the integer weights
        nx.set_edge_attributes(G_proj, weight, 'weight')
        # run all pairs analysis
        total_nodes = len(gdf_nodes_simple)
        print(
            f'  - Generate {neighbourhood_distance}m neighbourhoods '
            'for nodes (All pairs Dijkstra shortest path analysis)'
            )
        all_pairs_d = pd.DataFrame(
            [(k,v.keys()) for k,v in tqdm(
                nx.all_pairs_dijkstra_path_length(G_proj,chunk_size,'weight'),
                total=total_nodes,
                unit='nodes',
                desc=' '*18)],
            columns = ['osmid','nodes']
            ).set_index('osmid')
        # extract results
        print('  - Summarise attributes (average value from unique associated grid cells within nh buffer distance)...')
        result = pd.DataFrame(
            [tuple(
                grid.loc[gdf_nodes\
                            .loc[all_pairs_d.loc[n].nodes,'grid_id']\
                            .dropna()\
                            .unique(),
                           nh_grid_fields]\
                   .mean()\
                   .values) for index,n in tqdm(
                        np.ndenumerate(gdf_nodes_simple.index.values),
                        total=total_nodes,
                        desc=' '*18)],
            columns = [population_density,intersection_density],
            index = gdf_nodes_simple.index.values
            )
        gdf_nodes_simple = gdf_nodes_simple.join(result)
        # save in geopackage (so output files are all kept together)
        gdf_nodes_simple.to_file(
            gpkg, 
            layer = 'nodes_pop_intersect_density', 
            driver="GPKG"
            )
    print(
         "Time taken to calculate or load city local neighbourhood statistics: "
        f"{(time.time() - nh_startTime)/60:02g} mins"
        )
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
    gdf_nodes, gdf_edges = ox.graph_to_gdfs(G_proj)
    network = create_pdna_net(
        gdf_nodes, 
        gdf_edges, 
        predistance = accessibility_distance
        )
    distance_results = {}
    print("\nCalculating nearest node analyses ...")
    for analysis_key in indicators['nearest_node_analyses']:
        print(f'\n\t- {analysis_key}')
        analysis = indicators['nearest_node_analyses'][analysis_key]
        layer_analysis_count = len(analysis['layers'])
        for layer in analysis['layers']:
            if layer in input_layers and layer is not None:
                output_names = analysis['output_names'].copy()
                if layer_analysis_count > 1 and layer_analysis_count==len(analysis['output_names']):
                    # assume that output names correspond to layers, and refresh per analysis
                    output_names = [output_names[analysis['layers'].index(layer)]]
                print(f'\t\t{output_names}')
                gdf_poi = gpd.read_file(
                    analysis['geopackage'].format(gpkg = gpkg), 
                    layer = layer
                    )
                distance_results[f'{analysis}_{layer}'] = cal_dist_node_to_nearest_pois(
                    gdf_poi,
                    accessibility_distance,
                    network,
                    category_field = analysis['category_field'],
                    categories = analysis['categories'],
                    filter_field = analysis['filter_field'],
                    filter_iterations = analysis['filter_iterations'],
                    output_names = output_names,
                    output_prefix = 'sp_nearest_node_')
            else:
                # create null results --- e.g. for GTFS analyses where no layer exists
                distance_results[f'{analysis_key}_{layer}'] = pd.DataFrame(
                    index=gdf_nodes.index,
                    columns=[f'sp_nearest_node_{x}' for x in analysis['output_names']]
                    )
    # concatenate analysis dataframes into one
    gdf_nodes_poi_dist = pd.concat([gdf_nodes]+[distance_results[x] for x in distance_results], axis=1)
    # set index of gdf_nodes_poi_dist, using 'osmid' as the index, and remove other unnecessary columns
    gdf_nodes_poi_dist.set_index("osmid",inplace=True)
    unnecessary_columns = [x for x in
                             ["geometry", "grid_id", "lat", "lon", "y", "x", "highway", "ref"]
                                if x in gdf_nodes_poi_dist.columns]
    gdf_nodes_poi_dist.drop(unnecessary_columns,axis=1, inplace=True, errors="ignore")
    # replace -999 values (meaning no destination reached in less than 500 metres) as nan
    gdf_nodes_poi_dist = round(gdf_nodes_poi_dist, 0).replace(-999, np.nan).astype("Int64")
    # read sample points from disk (in city-specific geopackage)
    samplePointsData = gpd.read_file(gpkg, layer="urban_sample_points")
    # create 'grid_id' for sample point, if it not exists
    if "grid_id" not in samplePointsData.columns:
        samplePointsData = spatial_join_index_to_gdf(samplePointsData, grid, right_index_name='grid_id',join_type='within')
    print("Restrict sample points to those not located in grids with a population below "
          f"the minimum threshold value ({population['pop_min_threshold']})..."),
    below_minimum_pop_ids = list(grid.query(f'pop_est < {population["pop_min_threshold"]}').index.values)
    sample_point_length_pre_discard = len(samplePointsData)
    samplePointsData = samplePointsData[~samplePointsData.grid_id.isin(below_minimum_pop_ids)]
    sample_point_length_post_discard = len(samplePointsData)
    print(f"  {sample_point_length_pre_discard - sample_point_length_post_discard} sample points discarded, "
          f"leaving {sample_point_length_post_discard} remaining.")
    print("Restrict sample points to those with two associated sample nodes..."),
    sample_point_length_pre_discard = len(samplePointsData)
    samplePointsData = samplePointsData.query(
        f"n1 in {list(gdf_nodes_simple.index.values)} "
        f"and n2 in {list(gdf_nodes_simple.index.values)}"
        )
    sample_point_length_post_discard = len(samplePointsData)
    print(f"  {sample_point_length_pre_discard - sample_point_length_post_discard} sample points discarded, "
          f"leaving {sample_point_length_post_discard} remaining.")
    samplePointsData.set_index("point_id", inplace=True)
    distance_names = list(gdf_nodes_poi_dist.columns)
    # Estimate full distance to destinations for sample points
    full_nodes = create_full_nodes(
        samplePointsData,
        gdf_nodes_simple,
        gdf_nodes_poi_dist,
        distance_names,
        population_density,
        intersection_density,
    )
    samplePointsData = samplePointsData[["grid_id", "edge_ogc_fid", "geometry"]]\
        .join(full_nodes, how="left")
    # create binary access scores evaluated against accessibility distance
    # Options for distance decay accessibility scores are available in setup_sp.py module
    access_score_names = [f"{x.replace('nearest_node','access')}_score" for x in distance_names]
    samplePointsData[access_score_names] = binary_access_score(
        samplePointsData, 
        distance_names, 
        accessibility_distance
        )
    print("Calculating sample point specific analyses ...")
    # Defined in generated config file, e.g. daily living score, walkability index, etc
    for analysis in indicators['sample_point_analyses']:
        print(f"\t - {analysis}")
        for var in indicators['sample_point_analyses'][analysis]:
            columns = indicators['sample_point_analyses'][analysis][var]['columns']
            formula = indicators['sample_point_analyses'][analysis][var]['formula']
            axis    = indicators['sample_point_analyses'][analysis][var]['axis']
            if formula == "sum":
                samplePointsData[var] = samplePointsData[columns].sum(axis=axis)
            if formula == "max":
                samplePointsData[var] = samplePointsData[columns].max(axis=axis)
            if formula == "sum_of_z_scores":
                samplePointsData[var] = (
                    (samplePointsData[columns] -  samplePointsData[columns].mean()) \
                     / samplePointsData[columns].std()
                     ).sum(axis=1)
    # grid_id and edge_ogc_fid are integers
    samplePointsData[samplePointsData.columns[0:2]] = samplePointsData[samplePointsData.columns[0:2]].astype(int)
    # remaining non-geometry fields are float
    samplePointsData[samplePointsData.columns[3:]] = samplePointsData[samplePointsData.columns[3:]].astype(float)
    print("Save to geopackage...")
    # save the sample points with all the desired results to a new layer in geopackage
    samplePointsData = samplePointsData.reset_index()
    samplePointsData.to_file(
        gpkg, 
        layer="samplePointsData", 
        driver="GPKG"
        )
    endTime = time.time() - startTime
    print("Total time is : {:.2f} minutes".format(endTime / 60))

if __name__ == "__main__":
    main()
