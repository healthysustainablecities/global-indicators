"""
This script is to reproject the graphml
"""
import os
import osmnx as ox


def project_graphml(output_graphml, input_graphml, crs):
    output_path = os.path.join(
        dirname,
        'data', output_graphml
    )
    input_path = os.path.join(
        dirname, 'data',
        input_graphml
    )
    if os.path.isfile(output_path):
        print('projected graphml exists.')
    else:
        # else read original graphml and reproject it
        print('begin to reproject network')
        G = ox.load_graphml(input_path)
        G_proj = ox.project_graph(G, to_crs=crs)
        ox.save_graphml(
            G_proj,
            filename=output_graphml,
            folder=os.path.join(dirname, 'data'))
    print('Done')


if __name__ == '__main__':
    dirname = os.path.abspath('')
    output_graphml = 'phoenix_us_2019_10000m_pedestrian_osm_20190902_proj.graphml'
    input_graphml = 'phoenix_us_2019_10000m_pedestrian_osm_20190902.graphml'
    crs = {"init": "epsg:32612"}
    project_graphml(output_graphml, input_graphml, crs)
