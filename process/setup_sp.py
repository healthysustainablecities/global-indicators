################################################################################
# Module: setup_sp.py
# Description: this module contains functions to set up sample points stats within study regions

################################################################################

import os

import geopandas as gpd
import networkx as nx
import numpy as np
import pandana as pdna
import pandas as pd
from tqdm import tqdm
import osmnx as ox
import numpy

def read_proj_graphml(proj_graphml_filepath, ori_graphml_filepath, to_crs,undirected=True, retain_fields=None):
    """
    Read a projected graph from local disk if exist,
    otherwise, reproject origional graphml to the CRS appropriate for its geographic location,
    and save the projected graph to local disk

    Parameters
    ----------
    proj_graphml_filepath: string
        the projected graphml filepath
    ori_graphml_filepath: string
        the original graphml filepath
    to_crs: dict or string or pyproj.CRS
        project to this CRS
    undirected: bool (default: True)
        make graph undirected
    retain_edge_attributes = list (default: None)
        explicitly retain only a subset of edge attributes, else keep all (default)

    Returns
    -------
    networkx multidigraph
    """
    # if the projected graphml file already exist in disk, then load it from the path
    if os.path.isfile(proj_graphml_filepath):
        print("Read network from disk.")
        G_proj=ox.load_graphml(proj_graphml_filepath,int)
        if undirected:
            print("  - Ensure graph is undirected.")
            if G_proj.is_directed():
                G_proj = G_proj.to_undirected()
        return(G_proj)

    # else, read original study region graphml and reproject it
    else:
        print("Prepare network resources...")
        print("  - Read network from disk.")
        # load and project origional graphml from disk
        G = ox.load_graphml(ori_graphml_filepath,int)
        if retain_fields is not None:
            print("  - Remove unnecessary key data from edges")
            att_list = set([k for n in G.edges for k in G.edges[n].keys() if k not in ['osmid','length']])
            capture_output = [[d.pop(att, None) for att in att_list]
                                    for n1, n2, d in tqdm(G.edges(data=True),desc=' '*18)]
        del(capture_output)
        print("  - Project graph")
        G_proj = ox.project_graph(G, to_crs=to_crs)
        if undirected:    
            print("  - Ensure graph is undirected.")
            if G_proj.is_directed():
                G_proj = G_proj.to_undirected()
        print("  - Save projected graphml to disk")
        ox.save_graphml(G_proj, proj_graphml_filepath)
        return(G_proj)

def spatial_join_index_to_gdf(gdf, join_gdf, right_index_name,join_type='within'):
    """
    Append to a geodataframe the named index of another using spatial join

    Parameters
    ----------
    gdf: GeoDataFrame
    join_gdf: GeoDataFrame
    right_index_name: str (default: None)
    join_tyoe: str (default 'within')

    Returns
    -------
    GeoDataFrame
    """
    gdf_columns = list(gdf.columns)
    gdf = gpd.sjoin(gdf, join_gdf, how="left", op=join_type)
    if right_index_name is not None:
        gdf = gdf[gdf_columns+['index_right']]
        gdf.columns = gdf_columns+[right_index_name]
    return(gdf)

def create_pdna_net(gdf_nodes, gdf_edges, predistance=500):
    """
    Create pandana network to prepare for calculating the accessibility to destinations
    The network is comprised of a set of nodes and edges.

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
    gdf_nodes["x"] = gdf_nodes["geometry"].apply(lambda x: x.x)
    # Defines the y attribute for nodes in the network (e.g. latitude)
    gdf_nodes["y"] = gdf_nodes["geometry"].apply(lambda x: x.y)
    # Defines the node id that begins an edge
    gdf_edges["from"] = gdf_edges["u"].astype(np.int64)
    # Defines the node id that ends an edge
    gdf_edges["to"] = gdf_edges["v"].astype(np.int64)
    # Define the distance based on OpenStreetMap edges
    gdf_edges["length"] = gdf_edges["length"].astype(float)

    gdf_nodes["id"] = gdf_nodes["osmid"].astype(np.int64)
    gdf_nodes.set_index("id", inplace=True, drop=False)
    # Create the transportation network in the city
    # Typical data would be distance based from OSM or travel time from GTFS transit data
    net = pdna.Network(gdf_nodes["x"], gdf_nodes["y"], gdf_edges["from"], gdf_edges["to"], gdf_edges[["length"]])
    # Precomputes the range queries (the reachable nodes within this maximum distance)
    # so that aggregations don’t perform the network queries unnecessarily
    net.precompute(predistance + 10)
    return net


def cal_dist_node_to_nearest_pois(gdf_poi, distance, network, category_field = None, categories = None, filter_field = None, filter_iterations = None,output_names=None,output_prefix=''):
    """
    Calculate the distance from each node to the first nearest destination
    within a given maximum search distance threshold
    If the nearest destination is not within the distance threshold, then it will be coded as -999

    Parameters
    ----------
    gdf_poi: GeoDataFrame
        GeoDataFrame of destination point-of-interest
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
    gdf_poi["x"] = gdf_poi["geometry"].apply(lambda x: x.x)
    gdf_poi["y"] = gdf_poi["geometry"].apply(lambda x: x.y)
    if category_field is not None and categories is not None:
        # Calculate distances iterating over categories
        appended_data = []
        # establish output names
        if output_names is None:
                output_names = categories

        output_names = [f'{output_prefix}{x}' for x in output_names]
        # iterate over each destination category
        for x in categories:
            iteration = categories.index(x)
            # initialize the destination point-of-interest category
            # the positions are specified by the x and y columns (which are Pandas Series)
            # at a max search distance for up to the first nearest points-of-interest
            gdf_poi_filtered = gdf_poi.query(f"{category_field}=='{x}'")
            if len(gdf_poi_filtered) > 0:
                network.set_pois(
                    x,
                    distance,
                    1,
                    gdf_poi_filtered["x"],
                    gdf_poi_filtered["y"],
                )
                # return the distance to the first nearest destination category
                # if zero destination is within the max search distance, then coded as -999
                dist = network.nearest_pois(distance, x, 1, -999)

                # change the index name corresponding to each destination name
                dist.columns = dist.columns.astype(str)
                dist.rename(columns={"1": output_names[categories.index(x)]}, inplace=True)
            else:
                dist == pd.DataFrame(index=network.node_ids, columns=output_names[categories.index(x)])

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
            gdf_poi_filtered = gdf_poi.query(f"{filter_field}{x}")
            if len(gdf_poi_filtered) > 0:
                network.set_pois(
                    x,
                    distance,
                    1,
                    gdf_poi_filtered["x"],
                    gdf_poi_filtered["y"],
                )
                # return the distance to the first nearest destination category
                # if zero destination is within the max search distance, then coded as -999
                dist = network.nearest_pois(distance, x, 1, -999)

                # change the index name to match desired or default output
                dist.columns = dist.columns.astype(str)
                dist.rename(columns={"1": output_names[filter_iterations.index(x)]}, inplace=True)
            else:
                dist == pd.DataFrame(index=network.node_ids, columns=output_names[categories.index(x)])

            appended_data.append(dist)
        # return a GeoDataFrame with distance to the nearest destination from each source node
        gdf_poi_dist = pd.concat(appended_data, axis=1)
    else:
        if output_names is None:
            output_names = ['POI']

        output_names = [f'{output_prefix}{x}' for x in output_names]
        network.set_pois(output_names[0], distance, 1, gdf_poi["x"], gdf_poi["y"])
        gdf_poi_dist = network.nearest_pois(distance,output_names[0], 1, -999)
        # change the index name to match desired or default output
        gdf_poi_dist.columns = gdf_poi_dist.columns.astype(str)
        gdf_poi_dist.rename(columns={"1": output_names[0]}, inplace=True)

    return gdf_poi_dist


def create_full_nodes(
    samplePointsData,
    gdf_nodes_simple,
    gdf_nodes_poi_dist,
    distance_names,
    population_density,
    intersection_density,
):
    """
    Create long form working dataset of sample points to evaluate respective node distances and densities.

    This is achieved by first allocating sample points coincident with nodes their direct estimates, and then
    through a sub-function process_distant_nodes() deriving estimates for sample points based on terminal nodes
    of the edge segments on which they are located, accounting for respective distances.
    Parameters
    ----------
    samplePointsData: GeoDataFrame
        GeoDataFrame of sample points
    gdf_nodes_simple:  GeoDataFrame
        GeoDataFrame with density records
    gdf_nodes_poi_dist:  GeoDataFrame
        GeoDataFrame of distances to points of interest
    distance_names: list
        List of original distance field names
    population_density: str
        population density variable name
    intersection_density: str
        intersection density variable name

    Returns
    -------
    GeoDataFrame
    """
    print("Derive sample point estimates for accessibility and densities based on node distance relations")
    simple_nodes = gdf_nodes_poi_dist.join(gdf_nodes_simple)
    print("\t - match sample points whose locations coincide with intersections directly with intersection record data")
    coincident_nodes = samplePointsData.query('n1_distance==0')[['n1']]\
                        .rename({'n1':'node'},axis='columns')\
                        .append(samplePointsData.query('n1_distance!=0 and n2_distance==0')[['n2']]\
                                    .rename({'n2':'node'},axis='columns'))\
                        .join(simple_nodes, on="node", how="left")\
                      [[x for x in simple_nodes.columns if x not in ['hex_id','geometry']]].copy()
    distant_nodes = process_distant_nodes(samplePointsData,gdf_nodes_simple,gdf_nodes_poi_dist,distance_names,population_density,intersection_density)
    full_nodes = coincident_nodes.append(distant_nodes).sort_index()
    return full_nodes

def process_distant_nodes(
    samplePointsData,
    gdf_nodes_simple,
    gdf_nodes_poi_dist,
    distance_names,
    population_density,
    intersection_density,
):
    """
    Create long form working dataset of sample points to evaluate respective node distances and densities

    Parameters
    ----------
    samplePointsData: GeoDataFrame
        GeoDataFrame of sample points
    gdf_nodes_simple:  GeoDataFrame
        GeoDataFrame with density records
    gdf_nodes_poi_dist:  GeoDataFrame
        GeoDataFrame of distances to points of interest
    distance_names: list
        List of original distance field names
    population_density: str
        population density variable name
    intersection_density: str
        intersection density variable name

    Returns
    -------
    GeoDataFrame
    """
    print("\t - for sample points not co-located with intersections, derive estimates by:")
    print("\t\t - accounting for distances")
    distant_nodes = samplePointsData.query('n1_distance!=0 and n2_distance!=0')\
                        [["n1", "n2", "n1_distance", "n2_distance"]].copy()
    distant_nodes["nodes"] = distant_nodes.apply(lambda x: [[int(x.n1), x.n1_distance], [int(x.n2), x.n2_distance]], axis=1)
    distant_nodes = distant_nodes[["nodes"]].explode("nodes")
    distant_nodes[["node", "node_distance_m"]] = pd.DataFrame(distant_nodes.nodes.values.tolist(), index=distant_nodes.index)
    distant_nodes = distant_nodes[["node", "node_distance_m"]].join(gdf_nodes_poi_dist, on="node", how="left")
    distance_fields = []
    for d in distance_names:
        distant_nodes[d] = distant_nodes[d] + distant_nodes["node_distance_m"]
        distance_fields.append(d)
    
    distance_names = [x for x in distance_names if x in gdf_nodes_poi_dist.columns]
    print("\t\t - calculating proximity-weighted average of density statistics for each sample point")
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

    node_weight_denominator = distant_nodes["node_distance_m"].groupby(distant_nodes.index).sum()
    distant_nodes = distant_nodes[["node", "node_distance_m"] + distance_fields].join(node_weight_denominator,
                       how="left", rsuffix="_denominator")
    distant_nodes["density_weight"] = 1 - (distant_nodes["node_distance_m"] / distant_nodes["node_distance_m_denominator"])
    # join up full nodes with density fields
    distant_nodes = distant_nodes.join(gdf_nodes_simple[[population_density, intersection_density]], on="node", how="left")
    distant_nodes[population_density] = distant_nodes[population_density] * distant_nodes.density_weight
    distant_nodes[intersection_density] = distant_nodes[intersection_density] * distant_nodes.density_weight
    new_densities = [population_density, intersection_density]
    agg_functions = dict(
        zip(distance_fields + new_densities, ["min"] * len(distance_fields) + ["sum"] * len(new_densities))
    )
    distant_nodes = distant_nodes.groupby(distant_nodes.index).agg(agg_functions)
    return(distant_nodes)


#Cumulative opportunities (binary)
#1 if d <= access_dist
#0 if d > access_dist
def binary_access_score(df, new_name, old_name, access_dist):
    """
    Calculate accessibiity score using binary measure: 1 if access <= access_dist, 0 otherwise

    Parameters
    ----------
    df: DataFrame
        DataFrame with origin-destination distances
    new_name: list
        list of new field names for new access score
    old_name: list
         list of original field names for distances
    access_dist: int
        access distance threshold

    Returns
    -------
    DataFrame
    """
    df[new_name] = (df[old_name] <= access_dist).astype("Int64").fillna(0)
    return df[new_name]


#Soft threshold access score
#Higgs, C., Badland, H., Simons, K. et al. The Urban Liveability Index
def soft_access_score(df, new_name, old_name, access_dist, k):
    """
    Calculate accessibiity score using soft threshold approach:
    1 / (1+ e ^(k *((dist-access_dist)/access_dist)))

    Parameters
    ----------
    df: DataFrame
        DataFrame with origin-destination distances
    new_name: list
        list of new field names for new access score columns
    old_name: list
         list of original field names for distance columns
    access_dist: int
        access distance threshold
    k: int
        the slope of decay

    Returns
    -------
    DataFrame
    """
    df[new_name] = 1 / (1+numpy.exp(k * ((df[old_name]-access_dist) / access_dist)))

    df[new_name] = df[new_name].astype(float).fillna(0)
    return df[new_name]

#Cumulative-Gaussian
#Reference: Vale, D. S., & Pereira, M. (2017).
#The influence of the impedance function on gravity-based pedestrian accessibility measures
def Cumulative_Gaussian_access_score(df, new_name, old_name, access_dist, k):
    """
    Calculate accessibiity score using Cumulative-Gaussian approach:
    1 if d <= access_dist ; otherwise, e ^(-1 *((d^2)/k)) if d > access_dist

    Parameters
    ----------
    df: DataFrame
        DataFrame with origin-destination distances
    new_name: list
        list of new field names for new access score columns
    old_name: list
         list of original field names for distance columns
    access_dist: int
        access distance threshold
    k: int
        the slope of decay

    Returns
    -------
    DataFrame
    """
    df_access = pd.DataFrame()
    for n, d in zip(new_name, old_name): #loop through each colomn
        df[n] = 0 #create column

        df1=df[n].copy()
        df1.loc[df[d] > access_dist] = numpy.exp(-1 * (((df[d]-access_dist)**2) / k))
        df1.loc[df[d] <= access_dist] = 1

        df_access = pd.concat([df_access, df1], axis=1, ignore_index=False)

    df_access = df_access.astype(float).fillna(0)
    return df_access


def split_list(alist, wanted_parts=1):
    """
    split list

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
    return [alist[i * length // wanted_parts : (i + 1) * length // wanted_parts] for i in range(wanted_parts)]
