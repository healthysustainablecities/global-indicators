import osmnx as ox
import networkx as nx
import os
import pandas as pd
import geopandas as gpd
import time


def creatSubGraph(graphPath, gpkg_path, graphOutput):
    print('read original grapml, and save nodes and edges to geopackage.')
    G = ox.load_graphml(graphPath)
    nodes, edges = ox.graph_to_gdfs(G)
    # nodes = nodes.astype(str)
    columns = edges.columns.tolist()
    columns.remove('geometry')
    edges[columns] = edges[columns].astype(str)
    nodes.to_file(gpkg_path, layer='nodes_original', driver='GPKG')
    edges.to_file(gpkg_path, layer='edges_original', driver='GPKG')
    # sp = gpd.read_file(gpkg_path, layer='urban_sample_points')
    # nodesIds = pd.concat([sp.n1, sp.n2])
    # node_drop = nodesIds.drop_duplicates()
    # nodes = node_drop.tolist()
    # nodes_int = list(map(int, nodes))
    print('select nodes within study region buffer.')
    region_buffer = gpd.read_file(gpkg_path,
                                  layer='urban_study_region_buffered')
    nodes_withinbuffer = gpd.sjoin(nodes,
                                   region_buffer,
                                   how='inner',
                                   op='within')
    nodes_withinbuffer = nodes_withinbuffer.drop_duplicates(subset='osmid')
    nodesIds = nodes_withinbuffer.osmid.tolist()
    nodes_int = list(map(int, nodesIds))
    print('create sub grapml.')
    G_sub = G.subgraph(nodes_int).copy()
    # print(G_sub.nodes)
    print('save sub nodes and edges to geopackage.')
    nodes_sub, edges_sub = ox.graph_to_gdfs(G_sub)
    # nodes_sub = nodes_sub.astype(str)
    cols = edges_sub.columns.tolist()
    cols.remove('geometry')
    edges_sub[cols] = edges_sub[cols].astype(str)
    nodes_sub.to_file(gpkg_path, layer='nodes_subset', driver='GPKG')
    edges_sub.to_file(gpkg_path, layer='edges_subset', driver='GPKG')
    del nodes, edges
    del edges_sub, nodes_sub
    ox.save_graphml(G_sub,
                    filename=graphOutput,
                    folder=os.path.join(dirname, 'data'))


if __name__ == '__main__':
    startTime = time.time()
    print('begin to process')
    dirname = os.path.abspath('')
    graph_path = os.path.join(
        dirname,
        'data/phoenix_us_2019_10000m_pedestrian_osm_20190902_proj.graphml')
    gpkg_path = os.path.join(dirname,
                             'data/phoenix_us_2019_subset.gpkg')
    graph_output = 'phoenix_us_2019_10000m_pedestrian_osm_20190902_proj_subset.graphml'
    creatSubGraph(graph_path, gpkg_path, graph_output)
    print("finished, time is {}".format(time.time() - startTime))