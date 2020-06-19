################################################################################
# Module: setup_sp.py
# Description: this module contains functions to set up sample points stats within study regions

################################################################################

import osmnx as ox
import networkx as nx
import geopandas as gpd
import pandas as pd
import pandana as pdna
import numpy as np
from scipy.stats import zscore
import gc
import os
import csv


def read_proj_graphml(proj_graphml_filepath, ori_graphml_filepath, to_crs):
    """
    Read a projected graph from local disk if exist,
    otherwise, reproject origional graphml to the UTM zone appropriate for its geographic location,
    and save the projected graph to local disk

    Parameters
    ----------
    proj_graphml_filepath: string
        the projected graphml filepath
    ori_graphml_filepath: string
        the original graphml filepath
    to_crs: dict or string or pyproj.CRS
        project to this CRS

    Returns
    -------
    networkx multidigraph
    """
    # if the projected graphml file already exist in disk, then load it from the path
    if os.path.isfile(proj_graphml_filepath):
        print('Read network from disk.')
        return ox.load_graphml(proj_graphml_filepath)

    # else, read original study region graphml and reproject it
    else:
        print('Reproject network, and save the projected network to disk')


        # load and project origional graphml from disk
        G = ox.load_graphml(ori_graphml_filepath)
        G_proj = ox.project_graph(G, to_crs=to_crs)
        # save projected graphml to disk
        ox.save_graphml(G_proj, proj_graphml_filepath)

        return G_proj


def calc_sp_pop_intect_density_multi(G_proj, hexes, distance, rows, node, index):
    """
    Calculate population and intersection density for each sample point

    This function is for multiprocessing.
    A subnetwork will be created for each sample point as a neighborhood and then intersect the hexes
    with pop and intersection data. Population and intersection density for each sample point are caculated by averaging the intersected hexes density data

    Parameters
    ----------
    G_proj: networkx multidigraph
    hexes: GeoDataFrame
        hexagon layers containing pop and intersection info
    distance: int
        distance to search around the place geometry, in meters
    rows: int
        the number of rows to loop
    node: list
        the list of osmid of nodes
    index: int
        loop number

    Returns
    -------
    list
    """
    if index % 100 == 0:
        print('{0} / {1}'.format(index, rows))

    # create subgraph of neighbors centered at a node within a given radius.
    subgraph_proj = nx.ego_graph(G_proj,
                                 node,
                                 radius=distance,
                                 distance='length')
    # convert subgraph into edge GeoDataFrame
    subgraph_gdf = ox.graph_to_gdfs(subgraph_proj,
                                    nodes=False,
                                    edges=True,
                                    fill_edge_geometry=True)

    # intersect GeoDataFrame with hexes
    if len(subgraph_gdf) > 0:
        intersections = gpd.sjoin(hexes,
                                  subgraph_gdf,
                                  how='inner',
                                  op='intersects')

        # drop all rows where 'index_right' is nan
        intersections = intersections[intersections['index_right'].notnull()]
        # remove rows where 'index' is duplicate
        intersections = intersections.drop_duplicates(subset=['index'])
        # return list of nodes with osmid, pop and intersection density
        return [
            node,
            float(intersections['pop_per_sqkm'].mean()),
            float(intersections['intersections_per_sqkm'].mean())
        ]
    else:
        return [node]


def calc_sp_pop_intect_density(osmid, G_proj, hexes, field_pop, field_intersection,
                      distance, counter, rows):
    """
    Calculate population and intersection density for a sample point

    This function is apply the single thred method.
    A subnetwork will be created for each sample point as a neighborhood and then intersect the hexes
    with pop and intersection data. Population and intersection density for each sample point are caculated by averaging the intersected hexes density data


    Parameters
    ----------
    osmid: int
        the id of a node
    G_proj: networkx multidigraph
    hexes: GeoDataFrame
        hexagon layers containing pop and intersection info
    field_pop: str
        the field name of pop density
    field_intersection: str
        the field name of intersection density
    distance: int
        distance to search around the place geometry, in meters
    counter: value
        counter for process times(Object from multiprocessing)
    rows: int
        the number of rows to loop

    Returns
    -------
    Series
    """
    # apply calc_sp_pop_intect_density_single function to get population and intersection density for sample point
    pop_per_sqkm, int_per_sqkm = calc_sp_pop_intect_density_single(osmid, G_proj, hexes,
                                                    distance, counter, rows)
    return pd.Series({
        field_pop: pop_per_sqkm,
        field_intersection: int_per_sqkm
    })


def calc_sp_pop_intect_density_single(osmid, G_proj, hexes, distance, counter, rows):
    """
    Calculate population and intersection density for a sample point

    This function is for single thred.
    A subnetwork will be created for each sample point as a neighborhood and then intersect the hexes
    with pop and intersection data. Population and intersection density for each sample point are caculated by averaging the intersected hexes density data


    Parameters
    ----------
    osmid: int
        the id of a node
    G_proj: networkx multidigraph
    hexes: GeoDataFrame
        hexagon layers containing pop and intersection info
    distance: int
        distance to search around the place geometry, in meters
    counter: value
        counter for process times (object from multiprocessing)
    rows: int
        the number of rows to loop

    Returns
    -------
    tuple, (pop density, intersection density)
    """
    with counter.get_lock():
        counter.value += 1
        if counter.value % 100 == 0:
            print('{0} / {1}'.format(counter.value, rows))
    orig_node = osmid
    # create subgraph of neighbors centered at a node within a given radius.
    subgraph_proj = nx.ego_graph(G_proj,
                                 orig_node,
                                 radius=distance,
                                 distance='length')
    # convert subgraph into edge GeoDataFrame
    subgraph_gdf = ox.graph_to_gdfs(subgraph_proj,
                                    nodes=False,
                                    edges=True,
                                    fill_edge_geometry=True)
    # intersect sample point GeoDataFrame with hexes
    if len(subgraph_gdf) > 0:
        intersections = gpd.sjoin(hexes,
                                  subgraph_gdf,
                                  how='inner',
                                  op='intersects')
        # drop all rows where 'index_right' is nan
        intersections = intersections[intersections['index_right'].notnull()]
        # remove rows where 'index' is duplicate
        intersections = intersections.drop_duplicates(subset=['index'])
        # return tuple, pop and intersection density for sample point
        return (intersections['pop_per_sqkm'].mean(),
                intersections['intersections_per_sqkm'].mean())
    else:
        return (np.nan, np.nan)


def createHexid(sp, hex):
    """
    Create hex_id for sample point, if it not exists

    Parameters
    ----------
    sp: GeoDataFrame
        sample point GeoDataFrame
    hex: GeoDataFrame
        hexagon GeoDataFrame

    Returns
    -------
    GeoDataFrame
    """
    if 'hex_id' not in sp.columns.tolist():
        # get sample point dataframe columns
        print('Create hex_id for sample points')
        samplePoint_column = sp.columns.tolist()
        samplePoint_column.append('index')

        # join id from hex to each sample point
        samplePointsData = gpd.sjoin(sp, hex, how='left', op='within')
        samplePointsData = samplePointsData[samplePoint_column].copy()
        samplePointsData.rename(columns={'index': 'hex_id'}, inplace=True)
        return samplePointsData
    else:
        print("hex_id' already in sample point.")


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
    gdf_nodes['x'] = gdf_nodes['geometry'].apply(lambda x: x.x)
    # Defines the y attribute for nodes in the network (e.g. latitude)
    gdf_nodes['y'] = gdf_nodes['geometry'].apply(lambda x: x.y)
    # Defines the node id that begins an edge
    gdf_edges['from'] = gdf_edges['u'].astype(np.int64)
    # Defines the node id that ends an edge
    gdf_edges['to'] = gdf_edges['v'].astype(np.int64)
    # Define the distance based on OpenStreetMap edges
    gdf_edges['length'] = gdf_edges['length'].astype(float)

    gdf_nodes['id'] = gdf_nodes['osmid'].astype(np.int64)
    gdf_nodes.set_index('id', inplace=True, drop=False)
    # Create the transportation network in the city
    # Typical data would be distance based from OSM or travel time from GTFS transit data
    net = pdna.Network(gdf_nodes['x'], gdf_nodes['y'], gdf_edges['from'],
                       gdf_edges['to'], gdf_edges[['length']])
    # Precomputes the range queries (the reachable nodes within this maximum distance)
    # so that aggregations don’t perform the network queries unnecessarily
    net.precompute(predistance + 10)
    return net


def cal_dist_node_to_nearest_pois(gdf_poi, distance, network, *args, filterattr=True):
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
    args* : arguments
        list of field names of destination categories
    filterattr: bool
        indicate to public open space or not (default: {True})
        if False indicates to process public open space layer

    Returns
    -------
    GeoDataFrame
    """
    gdf_poi['x'] = gdf_poi['geometry'].apply(lambda x: x.x)
    gdf_poi['y'] = gdf_poi['geometry'].apply(lambda x: x.y)
    # if True, process the give open space layer
    if filterattr is True:
        appended_data = []
        # iterate over each destination category
        for x in args:
            # initialize the destination point-of-interest category
            # the positions are specified by the x and y columns (which are Pandas Series)
            # at a max search distance for up to the first nearest points-of-interest
            network.set_pois(x[0], distance, 1,
                             gdf_poi[gdf_poi['dest_name_full'] == x[0]]['x'],
                             gdf_poi[gdf_poi['dest_name_full'] == x[0]]['y'])
            # return the distance to the first nearest destination category
            # if zero destination is within the max search distance, then coded as -999
            dist = network.nearest_pois(distance, x[0], 1, -999)

            # important to convert columns index type to str
            dist.columns = dist.columns.astype(str)
            # change the index name corresponding to each destination name
            columnName = x[1]
            dist.rename(columns={'1': columnName}, inplace=True)
            appended_data.append(dist)
        # return a GeoDataFrame with distance to the nearest destination from each source node
        gdf_poi_dist = pd.concat(appended_data, axis=1)
        return gdf_poi_dist
    # if False, process the public open space layer
    else:
        for x in args:
            network.set_pois(x[0], distance, 1, gdf_poi['x'], gdf_poi['y'])
            dist = network.nearest_pois(distance, x[0], 1, -999)
            dist.columns = dist.columns.astype(str)
            columnName = x[1]
            dist.rename(columns={'1': columnName}, inplace=True)
            return dist


def convert_dist_to_binary(gdf, *columnNames, distance=500):
    """
    Convert numerical distance to binary, 0 or 1
    That is, if the numerical distance is greater than the accessibility distance (default 500),
    then it will be coded as 0, otherwise 1

    Parameters
    ----------
    gdf: GeoDataFrame
        GeoDataFrame with distance between nodes and nearest destination
    distance: int
        accessibility distance (default 500m) for evaluating binary indicators
    *columnNames: list
        list of column names of original dist columns and new binary columns
        eg. [[nearest_node_pos_dist], [nearest_node_pos_dist_binary]]

    Returns
    -------
    GeoDataFrame
    """
    for x in columnNames:
        #specify original column names with distance, and new binary column name
        columnName = x[0]
        columnBinary = x[1]
        # convert ditance value to 1 if the distance is no greater than the specified accessibility distance
        # indicating that the nearest destination is within the max accessibility distance threshold
        # otherwise,  replace distance value to 0
        gdf[columnBinary] = (gdf[columnName] <= distance).astype('Int64')
    return gdf


def cal_zscores(gdf, oriFieldNames, newFieldNames):
    """
    Calculate z-scores for variables

    Parameters
    ----------
    gdf: GeoDataFrame
    orifieldNames: list
        list contains origional field names of the columns needed to calculate zscores,
    newfieldNames: list
        list contains new field name after calculate the zscores

    Returns
    -------
    GeoDataFrame
    """
    #zip the old and new field names together
    fieldNames = list(zip(oriFieldNames, newFieldNames))
    for fields in fieldNames:
        #specify original field needed to calculate zscores, and the new field name after zscores
        orifield, newfield = fields[0], fields[1]
        #caluclate zscores within the GeoDataFrame
        gdf[newfield] = gdf[[orifield]].apply(zscore)
    return gdf


def create_full_nodes(samplePointsData, gdf_nodes_simple, gdf_nodes_poi_dist, dist_fieldNames, fulldist_FieldNames, pop_density, intersection_density):
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
    dist_fieldNames: list
        List of original distance field names
    fulldist_FieldNames: list
        List of full distance field names,
        the name order should be corresponding with dist_fieldNames1
    pop_density: str
        population density variable name
    intersection_density: str
        intersection density variable name

    Returns
    -------
    GeoDataFrame
    """
    full_nodes = samplePointsData[['n1', 'n2', 'n1_distance', 'n2_distance']].copy()

    full_nodes['nodes'] = full_nodes.apply(lambda x: [[int(x.n1),x.n1_distance],
                                                                  [int(x.n2),x.n2_distance]],
                                                       axis=1)
    full_nodes = full_nodes[['nodes']].explode('nodes')
    full_nodes[['node','node_distance_m']] = pd.DataFrame(
                                     full_nodes.nodes.values.tolist(),
                                     index= full_nodes.index)
    # join POIs results from nodes to sample points
    full_nodes = full_nodes[['node','node_distance_m']].join(gdf_nodes_poi_dist,
                                             on='node',
                                             how='left')
    distance_fields = []
    for d, v in zip(dist_fieldNames, fulldist_FieldNames):
        #here, it is better to adjust the config file regarding this output fieldname rather than here
        #new_d = d.replace('sp_nearest_node_','')+'_m'
        full_nodes[v] = full_nodes[d] + full_nodes['node_distance_m']
        distance_fields.append(v)
    # Calculate node density statistics
    node_weight_denominator = full_nodes['node_distance_m'].groupby(full_nodes.index).sum()
    full_nodes = full_nodes[['node','node_distance_m']+
                                                    distance_fields].join(
                                             node_weight_denominator,
                                             how='left',
                                             rsuffix='_denominator')
    full_nodes['density_weight'] = 1-(full_nodes['node_distance_m']/
                                        full_nodes['node_distance_m_denominator'])
    # Define a lambda function to compute the weighted mean:
    wm = lambda x: np.average(x, weights=full_nodes.loc[x.index, "density_weight"])
    # join up full nodes with density fields
    density_fields = [pop_density,intersection_density]
    full_nodes = full_nodes.join(
                           gdf_nodes_simple[density_fields],
                           on='node',
                           how='left')
    # define aggregation functions for per sample point estimates
    # ie. we take
    #       - minimum of full distances
    #       - and weighted mean of densities
    # The latter is so that if distance from two nodes for a point are 0m and 30m
    #  the weight of 0m is 1 and the weight of 30m is 0.
    #  ie. 1 - (0/(0+30)) = 1    , and 1 - (30/(0+30)) = 0
    #
    # This is not perfect; ideally the densities would be calculated for the sample points directly
    # But it is better than just assigning the value of the nearest node (which may be hundreds of metres away)
    full_nodes[pop_density] = full_nodes[pop_density]*full_nodes.density_weight
    full_nodes[intersection_density] = full_nodes[intersection_density]*full_nodes.density_weight
    new_densities = [pop_density,intersection_density]
    agg_functions = dict(zip(distance_fields+new_densities,
                               ['min']*len(distance_fields)+['sum']*len(new_densities)))
    full_nodes = full_nodes.groupby(
                              full_nodes.index
                              ).agg(agg_functions)
    # maybe treat this binary conversion in a seperate step? to keep the sanity of this funtions?
    #binary_fields = ['access_'+d.replace('_dist_m','') for d in distance_fields]
    #full_nodes[binary_fields] = (full_nodes[distance_fields] <= distance).astype('Int64')
    #this binary coverstion is moved to the convert_dist_to_binary function
    return(full_nodes)

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
    #return all parts in a list, like [[],[],[]]
    return [
        alist[i * length // wanted_parts:(i + 1) * length // wanted_parts]
        for i in range(wanted_parts)
    ]
