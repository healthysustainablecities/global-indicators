import osmnx as ox
import os
import sv_config as sc

if __name__ == '__main__':
    dirname = os.path.dirname(__file__)
    gpkg_output = os.path.join(dirname, sc.geopackagePath)
    graphml = os.path.join(dirname, sc.folder, sc.graphmlProj_name)
    graphml

    G = ox.load_graphml(graphml)
    nodes, edges = ox.graph_to_gdfs(G)
    for i in edges.columns.to_list():
        if i != 'geometry':
            edges[i] = edges[i].astype(str)

    nodes.to_file(gpkg_output, layer='nodes_origin', driver='GPKG')
    edges.to_file(gpkg_output, layer='edges_origin', driver='GPKG')   
