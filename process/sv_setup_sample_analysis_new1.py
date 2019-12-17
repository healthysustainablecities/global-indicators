import osmnx as ox
import networkx as nx
import geopandas as gpd
import pandas as pd
import pandana as pdna
import numpy as np
from scipy.stats import zscore
import gc
# from guppy import hpy
# from memory_profiler import profile


# @profile
def neigh_stats(G_proj, hexes, length, counter, rows, L, nodes,sindex=None):
    """
    Use hexes to do statistics for each sample point

    Parameters
    ----------
    osmid : int
        id of node

    G_proj : graphml
        OSM street network graphml

    hex: geodataframe 
        hexes using to intersect with network 

    length : float
        distance to search 

    Returns
    -------
    average densities of population and intersections 
    """
    # h = hpy()
    # tr = tracker.SummaryTracker()
    for node in nodes:
        with counter.get_lock():
            counter.value += 1
            if counter.value % 100 == 0:
                print('{0} / {1}'.format(counter.value, rows))
                # print (h.heap())
                # tr.print_diff()
        subgraph_proj = nx.ego_graph(G_proj,node,radius=length,distance='length')
        subgraph_gdf = ox.graph_to_gdfs(subgraph_proj,nodes=False,edges=True,fill_edge_geometry=True)
        del subgraph_proj
        gc.collect()
        # use subgraph to select interected hex250
        if len(subgraph_gdf) > 0:
            if sindex is None:
                intersections = gpd.sjoin(hexes,
                                          subgraph_gdf,
                                          how='inner',
                                          op='intersects')
                del subgraph_gdf
                gc.collect()
                # drop all rows where 'index_right' is nan
                intersections = intersections[
                    intersections['index_right'].notnull()]
                # remove rows where 'index' is duplicate
                intersections = intersections.drop_duplicates(subset=['index'])
            # ---------------------------------------------------------------
            # Rtree method: it's faster when the length is shorter, ,
            # but when the length grows up, it even slower than sjoin()
            else:
                possible_matches_index = list(
                    sindex.intersection(subgraph_gdf.cascaded_union.bounds))
                possible_matches = hexes.iloc[possible_matches_index]
                del possible_matches_index
                # must cascaded_union the subgraph. Otherwise, each hex that intersects
                # the subgraph will return
                intersections = possible_matches[possible_matches.intersects(
                    subgraph_gdf.cascaded_union)]
                del subgraph_gdf
                gc.collect()
                del possible_matches
                gc.collect()
            L.append([
                node, float(intersections['pop_per_sqkm'].mean()),
                float(intersections['intersections_per_sqkm'].mean())
            ])
            del intersections
            gc.collect()
        else:
            L.append([node])


def create_pdna_net(gdf_nodes, gdf_edges, predistance=500):
    """
    create the network in pandana to calculate the accessibility to 
    convenience, supermarket, etc.
    All destinations use the same network
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
    gdf_poi: geopandas dataframe
    network: pandana network
    args: the names of every subclass in one dataframe
         like ['supermarket', 'convenience', 'PT']
    filterattr: boolean
    default is True for process "destinations" layer
    False indicates to process "aos_nodes_30m_line" layer

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
    gdf: Geodataframe
    the data which includes the distances from nodes to each POI category
    columnName : Names of POI
    like['supermarket', 'convenience', 'PT']
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
    gdf: geopandas 
    dataframe of sample point 
    fieldNames: list
    the columns needed to calculate zscores
    """
    for fields in fieldNames:
        orifield, newfield = fields[0], fields[1]
        gdf[newfield] = gdf[[orifield]].apply(zscore)
    return gdf


def split_list(alist, wanted_parts=1):
    length = len(alist)
    return [
        alist[i * length // wanted_parts:(i + 1) * length // wanted_parts]
        for i in range(wanted_parts)
    ]
