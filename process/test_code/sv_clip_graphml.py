import geopandas as gpd
import osmnx as ox
import os
gpkgPath = r'C:\Users\zwa\Desktop\Project\5654_Global_Indicators_Project_RMIT\Code\global-indicators\sample_data\sample_odense.gpkg'
poly_region = gpd.read_file(gpkgPath, layer='sample_region')
# print(poly_region.shape)
poly_region = poly_region.to_crs({'init': 'epsg:4326'})

folder = r'C:\Users\zwa\Desktop\Project\5654_Global_Indicators_Project_RMIT\Code\global-indicators\sample_data'
polygon = poly_region['geometry'].iloc[0]
G = ox.graph_from_polygon(polygon, network_type='walk', retain_all=True)
G_proj = ox.project_graph(G, to_crs={'init': 'epsg:32632'})

nodes, edges = ox.graph_to_gdfs(G_proj)
nodes.to_file(os.path.join(folder, 'node_origin.shp'))
# !! important
fieldNames = list(edges.columns)
fieldNames.remove('geometry')
edges[fieldNames] = edges[fieldNames].astype(str)
edges.to_file(os.path.join(folder, 'edges_origin.shp'),encoding='utf-8')
ox.save_graphml(G_proj, filename='sample_graphml_proj', folder=folder)
