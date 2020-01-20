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


def neigh_stats(G_proj, hexes, length, rows, node, index):
    """
    This function is for multiprocessing.
    It uses hexes to calculate pop and intersection densiry for each sample point,
    it will create a subnetwork, and use that to intersect the hexes,
    then read info from the intersected hexes.
    -------
    average densities of population and intersections 

        G_proj {networkx} --  read from osmnx
        hexes {GeoDataFrame} -- hex
        length {int} -- distance to search 
        rows {int} -- the number of rows to loop
        nodes {list} -- the osmid of nodes
        index {int} -- loop number
    """
    if index % 100 == 0:
        print('{0} / {1}'.format(index, rows))
    subgraph_proj = nx.ego_graph(G_proj,
                                 node,
                                 radius=length,
                                 distance='length')
    subgraph_gdf = ox.graph_to_gdfs(subgraph_proj,
                                    nodes=False,
                                    edges=True,
                                    fill_edge_geometry=True)

    # use subgraph to select interected hex250
    if len(subgraph_gdf) > 0:
        intersections = gpd.sjoin(hexes,
                                  subgraph_gdf,
                                  how='inner',
                                  op='intersects')

        # drop all rows where 'index_right' is nan
        intersections = intersections[intersections['index_right'].notnull()]
        # remove rows where 'index' is duplicate
        intersections = intersections.drop_duplicates(subset=['index'])
        return [
            node,
            float(intersections['pop_per_sqkm'].mean()),
            float(intersections['intersections_per_sqkm'].mean())
        ]
    else:
        return [node]


def create_pdna_net(gdf_nodes, gdf_edges, predistance=500):
    """
    create the network in pandana to calculate the accessibility to 
    convenience, supermarket, etc.
    All destinations use the same network

    Arguments:
        gdf_nodes {GeoDataFrame} -- nodes
        gdf_edges {GeoDataFrame} -- edges

    Keyword Arguments:
        predistance {int} -- [the distance of search] (default: {500})

    Returns:
        [Network] -- the network created by pandana

    """

    gdf_nodes['x'] = gdf_nodes['geometry'].apply(lambda x: x.x)
    gdf_nodes['y'] = gdf_nodes['geometry'].apply(lambda x: x.y)
    gdf_edges['from'] = gdf_edges['u'].astype(np.int64)
    gdf_edges['to'] = gdf_edges['v'].astype(np.int64)
    gdf_edges['length'] = gdf_edges['length'].astype(float)

    gdf_nodes['id'] = gdf_nodes['osmid'].astype(np.int64)
    gdf_nodes.set_index('id', inplace=True, drop=False)

    net = pdna.Network(gdf_nodes['x'], gdf_nodes['y'], gdf_edges['from'],
                       gdf_edges['to'], gdf_edges[['length']])
    net.precompute(predistance + 10)
    return net


def cal_dist2poi(gdf_poi, distance, network, *args, filterattr=True):
    """
    calculate the distance from each node to POI

    Arguments:
        gdf_poi {GeoDataFrame} -- dataframe of POIs
        distance {int} -- the distance of search
        network {Network} -- pandana network
        args* -- field names

    Keyword Arguments:
        filterattr {bool} -- indicate to public open space or not (default: {True})
                             False indicates to process "aos_nodes_30m_line" layer
    Returns:
        GeoDataFrame -- the dataframe including new fields of result
    """
    gdf_poi['x'] = gdf_poi['geometry'].apply(lambda x: x.x)
    gdf_poi['y'] = gdf_poi['geometry'].apply(lambda x: x.y)
    if filterattr is True:
        appended_data = []
        for x in args:
            network.set_pois(x[0], distance, 1,
                             gdf_poi[gdf_poi['dest_name_full'] == x[0]]['x'],
                             gdf_poi[gdf_poi['dest_name_full'] == x[0]]['y'])
            dist = network.nearest_pois(distance, x[0], 1, -999)

            # important to convert columns index tpye tot str
            dist.columns = dist.columns.astype(str)
            # change the index name corresponding to each destination name
            columnName = x[1]
            dist.rename(columns={'1': columnName}, inplace=True)
            appended_data.append(dist)
        gdf_poi_dist = pd.concat(appended_data, axis=1)
        return gdf_poi_dist
    else:
        for x in args:
            network.set_pois(x[0], distance, 1, gdf_poi['x'], gdf_poi['y'])
            dist = network.nearest_pois(distance, x[0], 1, -999)
            dist.columns = dist.columns.astype(str)
            columnName = x[1]
            dist.rename(columns={'1': columnName}, inplace=True)
            return dist


def convert2binary(gdf, *columnNames):
    """
    convert distance to binary, 0 or 1
    Arguments:
        gdf {GeoDataFrame} -- some new fields will add to binary
        *columnNames -- Names of POIs
    Returns:
        GeoDataFrame -- the dataframe including new fields of result
    """
    for x in columnNames:
        columnName = x[0]
        columnBinary = x[1]
        gdf[columnBinary] = np.where(gdf[columnName] == -999, 0, 1)
    return gdf


# claculate z-scores for variables in sample point dataframe columns
def cal_zscores(gdf, fieldNames):
    """
    claculate z-scores for variables in sample point dataframe columns

    Arguments:
        gdf {GeoDataFrame} -- some new fields will add to zscore
        fieldNames {list} -- field names, the columns needed to calculate zscores

    Returns:
        GeoDataFrame -- the dataframe including zscores
    """
    for fields in fieldNames:
        orifield, newfield = fields[0], fields[1]
        gdf[newfield] = gdf[[orifield]].apply(zscore)
    return gdf


def split_list(alist, wanted_parts=1):
    """
    split list 

    Arguments:
        alist {list} -- the split list

    Keyword Arguments:
        wanted_parts {int} -- the number of parts (default: {1})

    Returns:
        list -- all parts in a list, like [[],[],[]]
    """
    length = len(alist)
    return [
        alist[i * length // wanted_parts:(i + 1) * length // wanted_parts]
        for i in range(wanted_parts)
    ]


def neigh_stats_single(osmid, G_proj, hexes, length, counter, rows):
    """
    This function is for single thread.
    It uses hexes to calculate pop and intersection densiry for each sample point,
    it will create a subnetwork, and use that to intersect the hexes,
    then read info from hexes.

    Arguments:
        osmid {int} -- the id of node
        G_proj {networkx} --  graphml
        hexes {GeoDataFrame} -- hex
        length {int} -- distance to search 
        counter {Value} -- counter for process times(Object from multiprocessing)
        rows {int} -- the number of rows to loop

    Returns:
        tuple -- the pop and intersection density
    """
    with counter.get_lock():
        counter.value += 1
        if counter.value % 100 == 0:
            print('{0} / {1}'.format(counter.value, rows))
    orig_node = osmid
    subgraph_proj = nx.ego_graph(G_proj,
                                 orig_node,
                                 radius=length,
                                 distance='length')
    subgraph_gdf = ox.graph_to_gdfs(subgraph_proj,
                                    nodes=False,
                                    edges=True,
                                    fill_edge_geometry=True)
    # use subgraph to select interected hex250
    if len(subgraph_gdf) > 0:
        intersections = gpd.sjoin(hexes,
                                  subgraph_gdf,
                                  how='inner',
                                  op='intersects')
        # drop all rows where 'index_right' is nan
        intersections = intersections[intersections['index_right'].notnull()]
        # remove rows where 'index' is duplicate
        intersections = intersections.drop_duplicates(subset=['index'])
        return (intersections['pop_per_sqkm'].mean(),
                intersections['intersections_per_sqkm'].mean())
    else:
        return (np.nan, np.nan)


def neigh_stats_apply(osmid, G_proj, hexes, field_pop, field_intersection,
                      length, counter, rows):
    """
    use pandas apply() to calculate poplulation density and intersections
    Arguments:
        osmid {int} -- the id of node
        G_proj {networkx} --  graphml
        hexes {GeoDataFrame} -- hex
        length {int} -- distance to search 
        counter {Value} -- counter for process times(Object from multiprocessing)
        rows {int} -- the number of rows to loop
        field_pop {str} -- the field name of pop density
        field_intersection {str} -- the field name of intersection density

    Returns:
        Series -- the result of pop and intersection density
    """
    pop_per_sqkm, int_per_sqkm = neigh_stats_single(osmid, G_proj, hexes,
                                                    length, counter, rows)
    return pd.Series({
        field_pop: pop_per_sqkm,
        field_intersection: int_per_sqkm
    })


def readGraphml(path, config):
    """read gramph from disk to memory

    Arguments:
        path {str} -- the path of the graphml
        config{dict} -- the dict read from json file

    Returns:
        networkx -- projected networkx
    """
    if os.path.isfile(path):
        print('Start to read network.')
        return ox.load_graphml(path)
    else:
        # else read original graphml and reproject it
        print('Start to reproject network')
        graphml_path = os.path.join(dirname, config["folder"],
                                    config["graphmlName"])
        G = ox.load_graphml(graphml_path)
        G_proj = ox.project_graph(G, to_crs=config["to_crs"])
        ox.save_graphml(G_proj,
                        filename=config["graphmlProj_name"],
                        folder=os.path.join(dirname, config["folder"]))

        return G_proj


def createHexid(sp, hex):
    """create hex_id for sample point, if it not exists

    Arguments:
        sp {GeoDataFrame} -- sample point
        hex {GeoDataFrame} -- hex
    Returns:
        GeoDataFrame -- sample point
    """
    if "hex_id" not in sp.columns.tolist():
        # get sample point dataframe columns
        print("Start to create hex_id for sample points")
        samplePoint_column = sp.columns.tolist()
        samplePoint_column.append('index')

        # join id from hex to each sample point
        samplePointsData = gpd.sjoin(sp, hex, how='left', op='within')
        samplePointsData = samplePointsData[samplePoint_column].copy()
        samplePointsData.rename(columns={'index': 'hex_id'}, inplace=True)
        return samplePointsData
    else:
        print("'hex_id' already in sample point.")
