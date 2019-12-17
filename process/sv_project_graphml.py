import os
import osmnx as ox
dirname = os.path.abspath('')
graphmlProj_path = os.path.join(
    dirname,
    'data/phoenix_us_2019_10000m_pedestrian_osm_20190902_proj.graphml')

if os.path.isfile(graphmlProj_path):
    print('projected graphml exists.')
else:
    # else read original graphml and reproject it
    print('begin to reproject network')
    graphml_path = os.path.join(
        dirname, 'data/phoenix_us_2019_10000m_pedestrian_osm_20190902.graphml')
    G = ox.load_graphml(graphml_path)
    G_proj = ox.project_graph(G, to_crs={"init": "epsg:32612"})
    ox.save_graphml(
        G_proj,
        filename='phoenix_us_2019_10000m_pedestrian_osm_20190902_proj.graphml',
        folder=os.path.join(dirname, 'data'))
print('Done')
