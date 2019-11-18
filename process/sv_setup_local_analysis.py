import osmnx as ox
import networkx as nx
import os
import geopandas as gpd
import sv_config as sc


def neigh_stats(gpd_series, G_proj, hexes, length=1600):
    """
    Use hexes to do statistics for each sample point

    Parameters
    ----------
    gpd_series : geopandas Series
        the geodataframe of sample points

    G_proj : graphml
        OSM street network graphml

    hex: geodataframe 
        hexes using to intersect with network 

    length : float
        distance to search 

    Returns
    -------
    subgraph geodataframe
    """

    # locate closest node on network to do statistics on each sample point
    # orig_point is (y,x)
    orig_point = (gpd_series.y, gpd_series.x)
    orig_node = ox.get_nearest_node(
        G_proj, orig_point, method='euclidean', return_dist=True)
    subgraph_proj = nx.ego_graph(
        G_proj, orig_node[0], radius=length, distance='length')
    subgraph_gdf = ox.graph_to_gdfs(
        subgraph_proj, nodes=False, edges=True, fill_edge_geometry=True)
    # use subgraph to select interected hex250
    if len(subgraph_gdf) > 0:
        # sjoin takes 12s for each sample point
        intersections = gpd.sjoin(
            hexes, subgraph_gdf, how='left', op='intersects')
        # drop all rows where 'index_right' is nan
        intersections = intersections[intersections['index_right'].notnull()]
        # remove rows where 'index' is duplicate
        intersections = intersections.drop_duplicates(subset=['index'])
        # dirname = os.path.dirname(__file__)
        # intersections[['index', 'geometry', 'index_right']].to_file(
        #     os.path.join(dirname, '../data/intersectHex.shp'))


        # this method takes 22s for each sample point
        subgraph_gdf = subgraph_gdf.unary_union
        hexes['intersect'] = hexes.intersects(subgraph_gdf)

    else:
        print('there is no network')
    # output is smaple point subgraph with buffer polygon geometry and original node id reference
    return 'abc'

################################################################################
