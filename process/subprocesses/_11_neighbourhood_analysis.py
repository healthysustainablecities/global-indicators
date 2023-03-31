"""
Neighbourhood analysis.

This script creates neighbourhood indicators for sample points.  To run it, supply a study region code name.

It assumes network projected network nodes and edges have been generated and stored in a PostGIS database, which can be read from as a GeoDataFrame to generate a graph.

Once run, the sample points may be aggregated to a neighbourhood small area grid and for overall
city summaries by running 03_aggregation.py.

As a result of running the script, a layer is added to the study region's geopackage file
containing sample point indicators ("sample_points").  These indicators include:
1. average population and intersection density per sample sample point
2. accessibility, dailyliving and walkability score per sample point
"""

import os
import sys
import time

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd

# Set up project and region parameters for GHSCIC analyses
from _project_setup import *
from geoalchemy2 import Geometry
from setup_sp import (
    binary_access_score,
    cal_dist_node_to_nearest_pois,
    create_full_nodes,
    create_pdna_net,
    filter_ids,
    spatial_join_index_to_gdf,
)
from sqlalchemy import create_engine, inspect, text
from tqdm import tqdm

# Hard coded density variable names
population_density = 'sp_local_nh_avg_pop_density'
intersection_density = 'sp_local_nh_avg_intersection_density'


def main():
    startTime = time.time()
    engine = create_engine(
        f'postgresql://{db_user}:{db_pwd}@{db_host}/{db}',
        pool_pre_ping=True,
        connect_args={
            'keepalives': 1,
            'keepalives_idle': 30,
            'keepalives_interval': 10,
            'keepalives_count': 5,
        },
    )
    db_contents = inspect(engine)
    with engine.connect() as connection:
        nodes = gpd.read_postgis(
            'nodes_simplified', connection, index_col='osmid',
        )
    with engine.connect() as connection:
        edges = gpd.read_postgis(
            'edges_simplified', connection, index_col=['u', 'v', 'key'],
        )
    G_proj = ox.graph_from_gdfs(nodes, edges, graph_attrs=None)
    with engine.connect() as connection:
        grid = gpd.read_postgis(
            population_grid, connection, index_col='grid_id',
        )
    print(
        '\nFirst pass node-level neighbourhood analysis (Calculate average population and intersection density '
        'for each intersection node in study regions, taking mean values from distinct grid cells within '
        'neighbourhood buffer distance)',
    )
    nh_startTime = time.time()
    # read from disk if exist
    if db_contents.has_table('nodes_pop_intersect_density'):
        print('  - Read population and intersection density from database.')
        with engine.connect() as connection:
            gdf_nodes_simple = gpd.read_postgis(
                'nodes_pop_intersect_density',
                connection,
                index_col='osmid',
                geom_col='geometry',
            )
    else:
        print('  - Set up simple nodes')
        gdf_nodes = ox.graph_to_gdfs(G_proj, nodes=True, edges=False)
        # associate nodes with id
        gdf_nodes = spatial_join_index_to_gdf(gdf_nodes, grid, dropna=False)
        # keep only the unique node id column
        gdf_nodes = gdf_nodes[['grid_id', 'geometry']]
        # drop any nodes which are na
        # (they are outside the buffered study region and not of interest)
        gdf_nodes_simple = gdf_nodes[~gdf_nodes.grid_id.isna()].copy()
        gdf_nodes = gdf_nodes[['grid_id']]
    if (
        len(
            [
                x
                for x in [population_density, intersection_density]
                if x not in gdf_nodes_simple.columns
            ],
        )
        > 0
    ):
        # Calculate average population and intersection density for each intersection node in study regions
        # taking mean values from distinct grid cells within neighbourhood buffer distance
        nh_grid_fields = ['pop_per_sqkm', 'intersections_per_sqkm']
        # Create a dictionary of edge index and integer values of length
        # The length attribute was saved as string, so must be recast to use as weight
        # The units are meters, so the decimal precision is unnecessary (error is larger than this; meter is adequate)
        weight = dict(
            zip(
                [k for k in G_proj.edges],
                [int(float(G_proj.edges[k]['length'])) for k in G_proj.edges],
            ),
        )
        # Add a new edge attribute using the integer weights
        nx.set_edge_attributes(G_proj, weight, 'weight')
        # run all pairs analysis
        total_nodes = len(gdf_nodes_simple)
        print(
            f'  - Generate {neighbourhood_distance}m neighbourhoods '
            'for nodes (All pairs Dijkstra shortest path analysis)',
        )
        all_pairs_d = pd.DataFrame(
            [
                (k, v.keys())
                for k, v in tqdm(
                    nx.all_pairs_dijkstra_path_length(
                        G_proj, chunk_size, 'weight',
                    ),
                    total=total_nodes,
                    unit='nodes',
                    desc=' ' * 18,
                )
            ],
            columns=['osmid', 'nodes'],
        ).set_index('osmid')
        # extract results
        print(
            '  - Summarise attributes (average value from unique associated grid cells within nh buffer distance)...',
        )
        result = pd.DataFrame(
            [
                tuple(
                    grid.loc[
                        gdf_nodes.loc[all_pairs_d.loc[n].nodes, 'grid_id']
                        .dropna()
                        .unique(),
                        nh_grid_fields,
                    ]
                    .mean()
                    .values,
                )
                for index, n in tqdm(
                    np.ndenumerate(gdf_nodes_simple.index.values),
                    total=total_nodes,
                    desc=' ' * 18,
                )
            ],
            columns=[population_density, intersection_density],
            index=gdf_nodes_simple.index.values,
        )
        gdf_nodes_simple = gdf_nodes_simple.join(result)
        # save in geopackage (so output files are all kept together)
        with engine.connect() as connection:
            gdf_nodes_simple.to_postgis(
                'nodes_pop_intersect_density', connection, index='osmid',
            )
    print(
        'Time taken to calculate or load city local neighbourhood statistics: '
        f'{(time.time() - nh_startTime)/60:.02f} mins',
    )
    # Calculate accessibility to points of interest and walkability for sample points:
    # 1. using pandana packadge to calculate distance to access from sample
    #    points to destinations (daily living destinations, public open space)
    # 2. calculate accessibiity score per sample point: transform accessibility
    #    distance to binary measure: 1 if access <= 500m, 0 otherwise
    # 3. calculate daily living score by summing the accessibiity scores to all
    #    POIs (excluding pos)
    # 4. calculate walkability score per sample point: get zscores for daily
    #    living accessibility, populaiton density and intersections population_density;
    #    sum these three zscores at sample point level
    print('\nCalculate accessibility to points of interest.')
    gdf_nodes, gdf_edges = ox.graph_to_gdfs(G_proj)
    network = create_pdna_net(
        gdf_nodes, gdf_edges, predistance=accessibility_distance,
    )
    distance_results = {}
    print('\nCalculating nearest node analyses ...')
    for analysis_key in indicators['nearest_node_analyses']:
        print(f'\n\t- {analysis_key}')
        analysis = indicators['nearest_node_analyses'][analysis_key]
        layer_analysis_count = len(analysis['layers'])
        gdf_poi_layers = {}
        for layer in analysis['layers']:
            if db_contents.has_table(layer) and layer is not None:
                output_names = analysis['output_names'].copy()
                if layer_analysis_count > 1 and layer_analysis_count == len(
                    analysis['output_names'],
                ):
                    # assume that output names correspond to layers, and refresh per analysis
                    output_names = [
                        output_names[analysis['layers'].index(layer)],
                    ]
                print(f'\t\t{output_names}')
                if layer not in gdf_poi_layers:
                    with engine.connect() as connection:
                        gdf_poi_layers[layer] = gpd.read_postgis(
                            layer, connection,
                        )
                distance_results[
                    f'{analysis}_{layer}'
                ] = cal_dist_node_to_nearest_pois(
                    gdf_poi_layers[layer],
                    geometry='geom',
                    distance=accessibility_distance,
                    network=network,
                    category_field=analysis['category_field'],
                    categories=analysis['categories'],
                    filter_field=analysis['filter_field'],
                    filter_iterations=analysis['filter_iterations'],
                    output_names=output_names,
                    output_prefix='sp_nearest_node_',
                )
            else:
                # create null results --- e.g. for GTFS analyses where no layer exists
                distance_results[f'{analysis_key}_{layer}'] = pd.DataFrame(
                    index=gdf_nodes.index,
                    columns=[
                        f'sp_nearest_node_{x}'
                        for x in analysis['output_names']
                    ],
                )
    # concatenate analysis dataframes into one
    gdf_nodes_poi_dist = pd.concat(
        [gdf_nodes] + [distance_results[x] for x in distance_results], axis=1,
    )
    unnecessary_columns = [
        x
        for x in [
            'geometry',
            'grid_id',
            'lat',
            'lon',
            'y',
            'x',
            'highway',
            'ref',
        ]
        if x in gdf_nodes_poi_dist.columns
    ]
    gdf_nodes_poi_dist.drop(
        unnecessary_columns, axis=1, inplace=True, errors='ignore',
    )
    # replace -999 values (meaning no destination reached in less than 500 metres) as nan
    gdf_nodes_poi_dist = (
        round(gdf_nodes_poi_dist, 0).replace(-999, np.nan).astype('Int64')
    )
    # read sample points from disk (in city-specific geopackage)
    with engine.connect() as connection:
        sample_points = gpd.read_postgis('urban_sample_points', connection)
    sample_points.columns = [
        'geometry' if x == 'geom' else x for x in sample_points.columns
    ]
    sample_points = filter_ids(
        df=sample_points,
        query=f"""n1 in {list(gdf_nodes_simple.index.values)} and n2 in {list(gdf_nodes_simple.index.values)}""",
        message='Restrict sample points to those with two associated sample nodes...',
    )
    sample_points.set_index('point_id', inplace=True)
    distance_names = list(gdf_nodes_poi_dist.columns)
    # Estimate full distance to destinations for sample points
    full_nodes = create_full_nodes(
        sample_points,
        gdf_nodes_simple,
        gdf_nodes_poi_dist,
        distance_names,
        population_density,
        intersection_density,
    )
    sample_points = sample_points[
        ['grid_id', 'edge_ogc_fid', 'geometry']
    ].join(full_nodes, how='left')
    # create binary access scores evaluated against accessibility distance
    # Options for distance decay accessibility scores are available in setup_sp.py module
    access_score_names = [
        f"{x.replace('nearest_node','access')}_score" for x in distance_names
    ]
    sample_points[access_score_names] = binary_access_score(
        sample_points, distance_names, accessibility_distance,
    )
    print('Calculating sample point specific analyses ...')
    # Defined in generated config file, e.g. daily living score, walkability index, etc
    for analysis in indicators['sample_point_analyses']:
        print(f'\t - {analysis}')
        for var in indicators['sample_point_analyses'][analysis]:
            columns = indicators['sample_point_analyses'][analysis][var][
                'columns'
            ]
            formula = indicators['sample_point_analyses'][analysis][var][
                'formula'
            ]
            axis = indicators['sample_point_analyses'][analysis][var]['axis']
            if formula == 'sum':
                sample_points[var] = sample_points[columns].sum(axis=axis)
            if formula == 'max':
                sample_points[var] = sample_points[columns].max(axis=axis)
            if formula == 'sum_of_z_scores':
                sample_points[var] = (
                    (sample_points[columns] - sample_points[columns].mean())
                    / sample_points[columns].std()
                ).sum(axis=1)
    # grid_id and edge_ogc_fid are integers
    sample_points[sample_points.columns[0:2]] = sample_points[
        sample_points.columns[0:2]
    ].astype(int)
    # remaining non-geometry fields are float
    sample_points[sample_points.columns[3:]] = sample_points[
        sample_points.columns[3:]
    ].astype(float)
    print('Save to database...')
    # save the sample points with all the desired results to a new layer in the database
    sample_points.columns = [
        'geom' if x == 'geometry' else x for x in sample_points.columns
    ]
    sample_points = sample_points.set_geometry('geom')
    with engine.connect() as connection:
        sample_points.to_postgis(
            point_summary, connection, index=True, if_exists='replace',
        )
    endTime = time.time() - startTime
    print(f'Total time is : {endTime / 60:.2f} minutes')


if __name__ == '__main__':
    main()
