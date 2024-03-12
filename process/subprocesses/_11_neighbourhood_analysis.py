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

# Set up project and region parameters for GHSCIC analyses
import ghsci
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from geoalchemy2 import Geometry
from script_running_log import script_running_log
from setup_sp import (
    binary_access_score,
    cal_dist_node_to_nearest_pois,
    create_full_nodes,
    create_pdna_net,
    filter_ids,
    spatial_join_index_to_gdf,
)
from tqdm import tqdm

# Hard coded density variable names
density_statistics = {
    'pop_per_sqkm': 'sp_local_nh_avg_pop_density',
    'intersections_per_sqkm': 'sp_local_nh_avg_intersection_density',
}


def node_level_neighbourhood_analysis(
    r, edges, nodes, neighbourhood_distance,
):
    """First pass node-level neighbourhood analysis (Calculate average population and intersection density for each intersection node in study regions, taking mean values from distinct grid cells within neighbourhood buffer distance."""
    nh_startTime = time.time()
    # read from disk if exist
    if 'nodes_pop_intersect_density' in r.tables:
        print('  - Read population and intersection density from database.')
        nodes_simple = r.get_gdf(
            'nodes_pop_intersect_density',
            index_col='osmid',
            geom_col='geometry',
        )
    else:
        G_proj = ox.graph_from_gdfs(
            nodes, edges, graph_attrs=None,
        ).to_undirected()
        grid = r.get_gdf(r.config['population_grid'], index_col='grid_id')
        print('  - Set up simple nodes')
        gdf_nodes = spatial_join_index_to_gdf(nodes, grid, dropna=False)
        # keep only the unique node id column
        gdf_nodes = gdf_nodes[['grid_id', 'geometry']]
        # drop any nodes which are na
        # (they are outside the buffered study region and not of interest)
        nodes_simple = gdf_nodes[~gdf_nodes.grid_id.isna()].copy()
        gdf_nodes = gdf_nodes[['grid_id']]
        # Calculate average population and intersection density for each intersection node in study regions
        # taking mean values from distinct grid cells within neighbourhood buffer distance
        nh_grid_fields = list(density_statistics.keys())
        # run all pairs analysis
        total_nodes = len(nodes_simple)
        print(
            f'  - Generate {neighbourhood_distance}m neighbourhoods '
            'for nodes (All pairs Dijkstra shortest path analysis)',
        )
        all_pairs_d = pd.DataFrame(
            [
                (k, v.keys())
                for k, v in tqdm(
                    nx.all_pairs_dijkstra_path_length(
                        G_proj, neighbourhood_distance, 'length',
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
                    np.ndenumerate(nodes_simple.index.values),
                    total=total_nodes,
                    desc=' ' * 18,
                )
            ],
            columns=list(density_statistics.values()),
            index=nodes_simple.index.values,
        )
        nodes_simple = nodes_simple.join(result)
        # save in geopackage (so output files are all kept together)
        with r.engine.connect() as connection:
            nodes_simple.to_postgis(
                'nodes_pop_intersect_density', connection, index='osmid',
            )
    print(
        'Time taken to calculate or load city local neighbourhood statistics: '
        f'{(time.time() - nh_startTime)/60:.02f} mins',
    )
    return nodes_simple


def calculate_poi_accessibility(r, ghsci, edges, nodes):
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
    network = create_pdna_net(
        nodes,
        edges,
        predistance=ghsci.settings['network_analysis'][
            'accessibility_distance'
        ],
    )
    distance_results = {}
    print('\nCalculating nearest node analyses ...')
    for analysis_key in ghsci.indicators['nearest_node_analyses']:
        print(f'\n\t- {analysis_key}')
        analysis = ghsci.indicators['nearest_node_analyses'][analysis_key]
        layer_analysis_count = len(analysis['layers'])
        gdf_poi_layers = {}
        for layer in analysis['layers']:
            if layer in r.tables and layer is not None:
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
                    gdf_poi_layers[layer] = r.get_gdf(layer)
                distance_results[
                    f'{analysis}_{layer}'
                ] = cal_dist_node_to_nearest_pois(
                    gdf_poi_layers[layer],
                    geometry='geom',
                    distance=ghsci.settings['network_analysis'][
                        'accessibility_distance'
                    ],
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
                    index=nodes.index,
                    columns=[
                        f'sp_nearest_node_{x}'
                        for x in analysis['output_names']
                    ],
                )
    # concatenate analysis dataframes into one
    nodes_poi_dist = pd.concat(
        [nodes] + [distance_results[x] for x in distance_results], axis=1,
    )
    nodes_poi_dist = nodes_poi_dist[
        [
            x
            for x in nodes_poi_dist.columns
            if x
            not in [
                'y',
                'x',
                'street_count',
                'lon',
                'lat',
                'ref',
                'highway',
                'geometry',
            ]
        ]
    ]
    # replace -999 values (meaning no destination reached in less than 500 metres) as nan
    nodes_poi_dist = (
        round(nodes_poi_dist, 0).replace(-999, np.nan).astype('Int64')
    )
    return nodes_poi_dist


def calculate_sample_point_access_scores(
    r,
    nodes_simple,
    nodes_poi_dist,
    density_statistics,
    accessibility_distance,
):
    # read sample points from disk (in city-specific geopackage)
    sample_points = r.get_gdf('urban_sample_points')
    sample_points.columns = [
        'geometry' if x == 'geom' else x for x in sample_points.columns
    ]
    sample_points = filter_ids(
        df=sample_points,
        query=f"""n1 in {list(nodes_simple.index.values)} and n2 in {list(nodes_simple.index.values)}""",
        message='Restrict sample points to those with two associated sample nodes...',
    )
    sample_points.set_index('point_id', inplace=True)
    # Estimate full distance to destinations for sample points
    full_nodes = create_full_nodes(
        sample_points,
        nodes_simple,
        nodes_poi_dist,
        list(density_statistics.values()),
    )
    sample_points = sample_points[
        ['grid_id', 'edge_ogc_fid', 'geometry']
    ].join(full_nodes, how='left')
    # create binary access scores evaluated against accessibility distance
    # Options for distance decay accessibility scores are available in setup_sp.py module
    distance_names = list(nodes_poi_dist.columns)
    access_score_names = [
        f"{x.replace('nearest_node','access')}_score" for x in distance_names
    ]
    sample_points[access_score_names] = binary_access_score(
        sample_points, distance_names, accessibility_distance,
    )
    return sample_points


def calculate_sample_point_indicators(
    ghsci, sample_points,
):
    print('Calculating sample point specific analyses ...')
    # Defined in generated config file, e.g. daily living score, walkability index, etc
    for analysis in ghsci.indicators['sample_point_analyses']:
        print(f'\t - {analysis}')
        for var in ghsci.indicators['sample_point_analyses'][analysis]:
            columns = ghsci.indicators['sample_point_analyses'][analysis][var][
                'columns'
            ]
            formula = ghsci.indicators['sample_point_analyses'][analysis][var][
                'formula'
            ]
            axis = ghsci.indicators['sample_point_analyses'][analysis][var][
                'axis'
            ]
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
    return sample_points


def neighbourhood_analysis(codename):
    start = time.time()
    script = '_11_neighbourhood_analysis'
    task = 'Analyse neighbourhood indicators for sample points'
    r = ghsci.Region(codename)
    nodes = r.get_gdf('nodes', index_col='osmid')
    nodes.columns = ['geometry' if x == 'geom' else x for x in nodes.columns]
    nodes = nodes.set_geometry('geometry')
    edges = r.get_gdf('edges_simplified', index_col=['u', 'v', 'key'])
    edges.columns = ['geometry' if x == 'geom' else x for x in edges.columns]
    edges = edges.set_geometry('geometry')
    nodes_simple = node_level_neighbourhood_analysis(
        r,
        edges,
        nodes,
        ghsci.settings['network_analysis']['neighbourhood_distance'],
    )
    nodes_poi_dist = calculate_poi_accessibility(r, ghsci, edges, nodes)
    sample_points = calculate_sample_point_access_scores(
        r,
        nodes_simple,
        nodes_poi_dist,
        density_statistics,
        ghsci.settings['network_analysis']['accessibility_distance'],
    )
    sample_points = calculate_sample_point_indicators(ghsci, sample_points)

    print('Save to database...')
    # save the sample points with all the desired results to a new layer in the database
    sample_points.columns = [
        'geom' if x == 'geometry' else x for x in sample_points.columns
    ]
    sample_points = sample_points.set_geometry('geom')
    with r.engine.connect() as connection:
        sample_points.to_postgis(
            r.config['point_summary'],
            connection,
            index=True,
            if_exists='replace',
        )
    # output to completion log
    script_running_log(r.config, script, task, start)
    r.engine.dispose()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    neighbourhood_analysis(codename)


if __name__ == '__main__':
    main()
