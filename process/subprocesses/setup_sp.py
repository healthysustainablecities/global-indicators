"""
Define functions for spatial indicator analyses.

This module contains functions to set up sample points stats within study regions.
"""

import os

import geopandas as gpd
import networkx as nx
import numpy
import numpy as np
import osmnx as ox
import pandana as pdna
import pandas as pd
from tqdm import tqdm


def spatial_join_index_to_gdf(
    gdf,
    join_gdf,
    join_type='within',
    dropna=True,
):
    """Append to a geodataframe the named index of another using spatial join.

    Parameters
    ----------
    gdf: GeoDataFrame
    join_gdf: GeoDataFrame
    join_type: str (default 'within')
    dropna: True

    Returns
    -------
    GeoDataFrame
    """
    gdf_columns = list(gdf.columns)
    gdf = gpd.sjoin(gdf, join_gdf, how='left', predicate=join_type)
    if 'index_right' in gdf.columns:
        gdf = gdf.rename(columns={'index_right': join_gdf.index.name})
    gdf = gdf[gdf_columns + [join_gdf.index.name]]
    if dropna:
        gdf = gdf[~gdf[join_gdf.index.name].isna()]
        gdf[join_gdf.index.name] = gdf[join_gdf.index.name].astype(
            join_gdf.index.dtype,
        )
    return gdf


def filter_ids(df, query, message):
    """Pandas query designed to filter and report feedback on counts before and after query.

    Parameters
    ----------
    df: DataFrame
    query: str Pandas query string
    message: str An informative message to print describing query in plain language

    Returns
    -------
    DataFrame
    """
    print(message)
    pre_discard = len(df)
    df = df.query(query)
    post_discard = len(df)
    print(
        f'  {pre_discard - post_discard} sample points discarded, '
        f'leaving {post_discard} remaining.',
    )
    return df


def create_pdna_net(gdf_nodes, gdf_edges, predistance=500):
    """Create pandana network to prepare for calculating the accessibility to destinations The network is comprised of a set of nodes and edges.

    Parameters
    ----------
    gdf_nodes: GeoDataFrame
    gdf_edges: GeoDataFrame
    predistance: int
        the distance of search (in meters), default is 500 meters

    Returns
    -------
    pandana network
    """
    # Defines the x attribute for nodes in the network
    gdf_nodes['x'] = gdf_nodes['geometry'].apply(lambda x: x.x)
    # Defines the y attribute for nodes in the network (e.g. latitude)
    gdf_nodes['y'] = gdf_nodes['geometry'].apply(lambda x: x.y)
    # Defines the node id that begins an edge
    gdf_edges = gdf_edges.reset_index()
    gdf_edges['from'] = gdf_edges['u'].astype(np.int64)
    # Defines the node id that ends an edge
    gdf_edges['to'] = gdf_edges['v'].astype(np.int64)
    # Define the distance based on OpenStreetMap edges
    gdf_edges['length'] = gdf_edges['length'].astype(float)
    # Create the transportation network in the city
    # Typical data would be distance based from OSM or travel time from GTFS transit data
    net = pdna.Network(
        gdf_nodes['x'],
        gdf_nodes['y'],
        gdf_edges['from'],
        gdf_edges['to'],
        gdf_edges[['length']],
    )
    # Precomputes the range queries (the reachable nodes within this maximum distance)
    # so that aggregations don’t perform the network queries unnecessarily
    net.precompute(predistance + 10)
    return net


def cal_dist_node_to_nearest_pois(
    gdf_poi,
    geometry,
    distance,
    network,
    category_field=None,
    categories=None,
    filter_field=None,
    filter_iterations=None,
    output_names=None,
    output_prefix='',
):
    """Calculate the distance from each node to the first nearest destination within a given maximum search distance threshold If the nearest destination is not within the distance threshold, then it will be coded as -999.

    Parameters
    ----------
    gdf_poi: GeoDataFrame
        GeoDataFrame of destination point-of-interest
    geometry: str
        geometry column name
    distance: int
        the maximum search distance
    network: pandana network
    category_field: str
        a field which if supplied will be iterated over using values from 'categories' list  (default: None)
    categories : list
        list of field names of categories found in category_field (default: None)
    filter_field: str
        a field which if supplied will be iterated over to filter the POI dataframe using a query informed by an expression found in the filter iteration list.  Filters are only applied if a category has not been supplied (ie. use one or the other)  (default: None)
    filter_iterations : list
        list of expressions to query using the filter_field (default: None)
    output_names : list
        list of names which are used to rename the outputs; entries must have corresponding order to categories or filter iterations if these are supplied (default: None)
    output_prefix: str
        option prefix to append to supplied output_names list (default: '')

    Returns
    -------
    GeoDataFrame
    """
    gdf_poi['x'] = gdf_poi[geometry].apply(lambda x: x.x)
    gdf_poi['y'] = gdf_poi[geometry].apply(lambda x: x.y)
    if category_field is not None and categories is not None:
        # Calculate distances iterating over categories
        appended_data = []
        # establish output names
        if output_names is None:
            output_names = categories

        output_names = [f'{output_prefix}{x}' for x in output_names]
        # iterate over each destination category
        for x in categories:
            # initialize the destination point-of-interest category
            # the positions are specified by the x and y columns (which are Pandas Series)
            # at a max search distance for up to the first nearest points-of-interest
            gdf_poi_filtered = gdf_poi.query(f"{category_field}=='{x}'")
            if len(gdf_poi_filtered) > 0:
                network.set_pois(
                    x,
                    distance,
                    1,
                    gdf_poi_filtered['x'],
                    gdf_poi_filtered['y'],
                )
                # return the distance to the first nearest destination category
                # if zero destination is within the max search distance, then coded as -999
                dist = network.nearest_pois(distance, x, 1, -999)

                # change the index name corresponding to each destination name
                dist.columns = dist.columns.astype(str)
                dist.rename(
                    columns={'1': output_names[categories.index(x)]},
                    inplace=True,
                )
            else:
                dist = pd.DataFrame(
                    index=network.node_ids,
                    columns=output_names[categories.index(x)],
                )

            appended_data.append(dist)
        # return a GeoDataFrame with distance to the nearest destination from each source node
        gdf_poi_dist = pd.concat(appended_data, axis=1)
    elif filter_field is not None and filter_iterations is not None:
        # Calculate distances across filtered iterations
        appended_data = []
        # establish output names
        if output_names is None:
            output_names = filter_iterations

        output_names = [f'{output_prefix}{x}' for x in output_names]
        # iterate over each destination category
        for x in filter_iterations:
            # initialize the destination point-of-interest category
            # the positions are specified by the x and y columns (which are Pandas Series)
            # at a max search distance for up to the first nearest points-of-interest
            gdf_poi_filtered = gdf_poi.query(f'{filter_field}{x}')
            if len(gdf_poi_filtered) > 0:
                network.set_pois(
                    x,
                    distance,
                    1,
                    gdf_poi_filtered['x'],
                    gdf_poi_filtered['y'],
                )
                # return the distance to the first nearest destination category
                # if zero destination is within the max search distance, then coded as -999
                dist = network.nearest_pois(distance, x, 1, -999)

                # change the index name to match desired or default output
                dist.columns = dist.columns.astype(str)
                dist.rename(
                    columns={'1': output_names[filter_iterations.index(x)]},
                    inplace=True,
                )
            else:
                dist == pd.DataFrame(
                    index=network.node_ids,
                    columns=output_names[categories.index(x)],
                )

            appended_data.append(dist)
        # return a GeoDataFrame with distance to the nearest destination from each source node
        gdf_poi_dist = pd.concat(appended_data, axis=1)
    else:
        if output_names is None:
            output_names = ['POI']

        output_names = [f'{output_prefix}{x}' for x in output_names]
        network.set_pois(
            output_names[0],
            distance,
            1,
            gdf_poi['x'],
            gdf_poi['y'],
        )
        gdf_poi_dist = network.nearest_pois(distance, output_names[0], 1, -999)
        # change the index name to match desired or default output
        gdf_poi_dist.columns = gdf_poi_dist.columns.astype(str)
        gdf_poi_dist.rename(columns={'1': output_names[0]}, inplace=True)

    return gdf_poi_dist


def create_full_nodes(
    samplePointsData,
    gdf_nodes_simple,
    gdf_nodes_poi_dist,
    density_statistics,
):
    """Create long form working dataset of sample points to evaluate respective node distances and densities.

    This is achieved by first allocating sample points coincident with nodes their direct estimates, and then through a sub-function process_distant_nodes() deriving estimates for sample points based on terminal nodes of the edge segments on which they are located, accounting for respective distances.

    Parameters
    ----------
    samplePointsData: GeoDataFrame
        GeoDataFrame of sample points
    gdf_nodes_simple:  GeoDataFrame
        GeoDataFrame with density records
    gdf_nodes_poi_dist:  GeoDataFrame
        GeoDataFrame of distances to points of interest
    density_statistics: list
        list of density statistic sample point indicator names

    Returns
    -------
    GeoDataFrame
    """
    print(
        'Derive sample point estimates for accessibility and densities based on node distance relations',
    )
    simple_nodes = gdf_nodes_poi_dist.join(gdf_nodes_simple)
    print(
        '\t - match sample points whose locations coincide with intersections directly with intersection record data',
    )
    coincident_nodes = (
        pd.concat(
            [
                samplePointsData.query('n1_distance==0')[['n1']].rename(
                    {'n1': 'node'},
                    axis='columns',
                ),
                samplePointsData.query('n1_distance!=0 and n2_distance==0')[
                    ['n2']
                ].rename({'n2': 'node'}, axis='columns'),
            ],
        )
        .join(simple_nodes, on='node', how='left')[
            [
                x
                for x in simple_nodes.columns
                if x not in ['grid_id', 'geometry']
            ]
        ]
        .copy()
    )
    distant_nodes = process_distant_nodes(
        samplePointsData,
        gdf_nodes_simple,
        gdf_nodes_poi_dist,
        density_statistics,
    )
    full_nodes = pd.concat([coincident_nodes, distant_nodes]).sort_index()
    return full_nodes


def process_distant_nodes(
    samplePointsData,
    gdf_nodes_simple,
    gdf_nodes_poi_dist,
    density_statistics,
):
    """Create long form working dataset of sample points to evaluate respective node distances and densities.

    Parameters
    ----------
    samplePointsData: GeoDataFrame
        GeoDataFrame of sample points
    gdf_nodes_simple:  GeoDataFrame
        GeoDataFrame with density records
    gdf_nodes_poi_dist:  GeoDataFrame
        GeoDataFrame of distances to points of interest
    density_statistics: list
        list of density statistic sample point indicator names

    Returns
    -------
    GeoDataFrame
    """
    print(
        '\t - for sample points not co-located with intersections, derive estimates by:',
    )
    print('\t\t - accounting for distances')
    distant_nodes = samplePointsData.query(
        'n1_distance!=0 and n2_distance!=0',
    )[['n1', 'n2', 'n1_distance', 'n2_distance']].copy()
    distant_nodes['nodes'] = distant_nodes.apply(
        lambda x: [[int(x.n1), x.n1_distance], [int(x.n2), x.n2_distance]],
        axis=1,
    )
    distant_nodes = distant_nodes[['nodes']].explode('nodes')
    distant_nodes[['node', 'node_distance_m']] = pd.DataFrame(
        distant_nodes.nodes.values.tolist(),
        index=distant_nodes.index,
    )
    distant_nodes = distant_nodes[['node', 'node_distance_m']].join(
        gdf_nodes_poi_dist,
        on='node',
        how='left',
    )
    distance_fields = []
    for d in list(gdf_nodes_poi_dist.columns):
        distant_nodes[d] = distant_nodes[d] + distant_nodes['node_distance_m']
        distance_fields.append(d)

    print(
        '\t\t - calculating proximity-weighted average of density statistics for each sample point',
    )
    # define aggregation functions for per sample point estimates
    # ie. we take
    #       - minimum of full distances
    #       - and weighted mean of densities
    # The latter is so that if distance from two nodes for a point are 10m and 30m
    #  the weight of 10m is 0.75 and the weight of 30m is 0.25.
    #  ie. 1 - (10/(10+30)) = 0.75    , and 1 - (30/(10+30)) = 0.25
    # ie. the more proximal node is the dominant source of the density estimate, but the distal one still has
    # some contribution to ensure smooth interpolation across sample points (ie. a 'best guess' at true value).
    # This is not perfect; ideally the densities would be calculated for the sample points directly.
    # But it is better than just assigning the value of the nearest node (which may be hundreds of metres away).
    #
    # An important exceptional case which needs to be accounted for is a sample point co-located with a node
    # intersection which is the beginning and end of a cul-de-sac loop.  In such a case, n1 and n2 are identical,
    # and the distance to each is zero, which therefore results in a division by zero error. To resolve this issue,
    # and a general rule of efficiency, if distance to any node is zero that nodes esimates shall be employed directly.
    # This is why the weighting and full distance calculation is only considered for sample points with "distant nodes",
    # and not those with "coincident nodes".

    node_weight_denominator = (
        distant_nodes['node_distance_m'].groupby(distant_nodes.index).sum()
    )
    distant_nodes = distant_nodes[
        ['node', 'node_distance_m'] + distance_fields
    ].join(node_weight_denominator, how='left', rsuffix='_denominator')
    distant_nodes['density_weight'] = 1 - (
        distant_nodes['node_distance_m']
        / distant_nodes['node_distance_m_denominator']
    )
    # join up full nodes with density fields
    distant_nodes = distant_nodes.join(
        gdf_nodes_simple[density_statistics],
        on='node',
        how='left',
    )
    for statistic in density_statistics:
        distant_nodes[statistic] = (
            distant_nodes[statistic] * distant_nodes.density_weight
        )
    agg_functions = dict(
        zip(
            distance_fields + density_statistics,
            ['min'] * len(distance_fields) + ['sum'] * len(density_statistics),
        ),
    )
    distant_nodes = distant_nodes.groupby(distant_nodes.index).agg(
        agg_functions,
    )
    return distant_nodes


# Cumulative opportunities (binary)
# 1 if d <= access_dist
# 0 if d > access_dist
def binary_access_score(df, distance_names, threshold=500):
    """Calculate accessibiity score using binary measure.

    1 if access <= access_dist, 0 otherwise.

    Parameters
    ----------
    df: DataFrame
        DataFrame with origin-destination distances
    distance_names: list
        list of original distance field names
    threshold: int
        access distance threshold, default is 500 meters

    Returns
    -------
    DataFrame
    """
    df1 = (df[distance_names] <= threshold).fillna(False).astype(int)
    # If any of distance_names were all null in DF, should be returned as all null
    nulls = df[distance_names].isnull().all()
    df1[nulls.index[nulls]] = np.nan
    return df1


# Soft threshold access score
# Higgs, C., Badland, H., Simons, K. et al. (2019) The Urban Liveability Index
def soft_access_score(df, distance_names, threshold=500, k=5):
    """Calculate accessibiity score using soft threshold approach.

    1 / (1+ e^(k *((dist-access_dist)/access_dist)))

    Parameters
    ----------
    df: DataFrame
        DataFrame with origin-destination distances
    distance_names: list
        list of original distance field names
    threshold: int
        access distance threshold, default is 500 meters
    k: int
        the slope of decay, default is 5

    Returns
    -------
    DataFrame
    """
    df1 = 1 / (
        1 + numpy.exp(k * ((df[distance_names] - threshold) / threshold))
    )
    df1 = df1.fillna(0).astype(float)
    # If any of distance_names were all null in DF, should be returned as all null
    nulls = df[distance_names].isnull().all()
    df1[nulls.index[nulls]] = np.nan
    return df1


# Cumulative-Gaussian
# Reference: Vale, D. S., & Pereira, M. (2017).
# The influence of the impedance function on gravity-based pedestrian accessibility measures
def cumulative_gaussian_access_score(
    df,
    distance_names,
    threshold=500,
    k=129842,
):
    """Calculate accessibiity score using Cumulative-Gaussian approach.

    1 if d <= access_dist ; otherwise, e ^(-1 *((d^2)/k)) if d > access_dist

    Parameters
    ----------
    df: DataFrame
        DataFrame with origin-destination distances
    distance_names: list
        list of field names for distance records
    threshold: int
        access distance threshold
    k: int
        the slope of decay

    Returns
    -------
    DataFrame
    """
    df1 = df[distance_names].copy()
    df1 = df1.astype(float)
    df1[df1 <= threshold] = 1
    df1[df1 > threshold] = numpy.exp(
        -1 * (((df1[df1 > threshold] - threshold) ** 2) / k),
    )
    df1 = df1.fillna(0).astype(float)
    return df1


def split_list(alist, wanted_parts=1):
    """Split list.

    Parameters
    ----------
    alist: list
        the split list
    wanted_parts: int
        the number of parts (default: {1})

    Returns
    -------
    list
    """
    length = len(alist)
    # return all parts in a list, like [[],[],[]]
    return [
        alist[i * length // wanted_parts : (i + 1) * length // wanted_parts]
        for i in range(wanted_parts)
    ]
