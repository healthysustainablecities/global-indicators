import osmnx as ox
import networkx as nx
import os
import geopandas as gpd
import sv_config as sc
import pandas as pd


def neigh_stats(geom, G_proj, hexes, length=1600):
    """
    Use hexes to do statistics for each sample point

    Parameters
    ----------
    geom : shapely Point
        geometry of each sample points 

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

    # locate closest node on network to do statistics on each sample point
    # orig_point is (y,x)
    orig_point = (geom.y, geom.x)
    orig_node = ox.get_nearest_node(G_proj,
                                    orig_point,
                                    method='euclidean',
                                    return_dist=True)
    subgraph_proj = nx.ego_graph(G_proj,
                                 orig_node[0],
                                 radius=length,
                                 distance='length')
    subgraph_gdf = ox.graph_to_gdfs(subgraph_proj,
                                    nodes=False,
                                    edges=True,
                                    fill_edge_geometry=True)
    # use subgraph to select interected hex250
    if len(subgraph_gdf) > 0:
        # sjoin takes 12s for each sample point
        intersections = gpd.sjoin(hexes,
                                  subgraph_gdf,
                                  how='inner',
                                  op='intersects')
        # drop all rows where 'index_right' is nan
        intersections = intersections[intersections['index_right'].notnull()]
        # remove rows where 'index' is duplicate
        intersections = intersections.drop_duplicates(subset=['index'])

        # # Rtree method, the smaller of length, it's faster,
        # # but when the length grows up, it even slower than sjoin()
        # spatial_index = hexes.sindex
        # possible_matches_index = list(
        #     spatial_index.intersection(subgraph_gdf.cascaded_union.bounds))
        # possible_matches = hexes.iloc[possible_matches_index]
        # # must cascaded_union the subgraph. Otherwise, each hex that intersects
        # # the subgraph will return
        # intersections = possible_matches[possible_matches.intersects(
        #     subgraph_gdf.cascaded_union)]

        # dirname = os.path.dirname(__file__)
        # intersections[[
        #     'index', 'geometry', 'pop_per_sqkm', 'intersections_per_sqkm',
        #     'index_right'
        # ]].to_file(os.path.join(dirname, '../data/intersectHex.shp'))
        # if neigh_stats.counter == 100:
        #     print('!!!!!!!!!')
        # print(intersections['pop_per_sqkm'].mean())
        neigh_stats.counter += 1
        return (intersections['pop_per_sqkm'].mean(),
                intersections['intersections_per_sqkm'].mean())

    else:
        print('there is no network: {}'.format(neigh_stats.counter))
        # print(neigh_stats.counter)
        neigh_stats.counter += 1
        # the output is all 0 for these two columns
        return (0, 0)


neigh_stats.counter = 1

################################################################################


def neigh_stats_apply(geom, G_proj, hexes, length=1600):
    pop_per_sqkm, int_per_sqkm = neigh_stats(geom, G_proj, hexes, length)
    return pd.Series({
        'sp_local_nh_avg_pop_density': pop_per_sqkm,
        'sp_local_nh_avg_intersection_density': int_per_sqkm
    })


def neigh_stats_iterrows(sampleData, G_proj, hexes, length=1600):
    v1s, v2s = [], []
    for index, row in sampleData.iterrows():
        pop_per_sqkm, int_per_sqkm = neigh_stats(row['geometry'], G_proj,
                                                 hexes, length)
        v1s.append(pop_per_sqkm)
        v2s.append(int_per_sqkm)
    return pd.DataFrame({
        'sp_local_nh_avg_pop_density': v1s,
        'sp_local_nh_avg_intersection_density': v2s
    })
