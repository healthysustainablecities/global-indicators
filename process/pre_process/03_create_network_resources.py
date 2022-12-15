"""

OpenStreetMap network setup
~~~~~~~~~~~~~~~~~~~~~~~~~~~

::

    Script:  04_create_network_resources.py
    Purpose: Create pedestrian street networks for specified city

"""

import time
import os
import sys
import subprocess as sp
from datetime import datetime
import psycopg2 
import networkx as nx
import osmnx as ox
from shapely.geometry import shape, MultiPolygon, Polygon
import geopandas as gpd
from sqlalchemy import create_engine,inspect
from geoalchemy2 import Geometry, WKTElement

from script_running_log import script_running_log

# Set up project and region parameters for GHSCIC analyses
from _project_setup import *

def main():
    # simple timer for log file
    start = time.time()
    script = os.path.basename(sys.argv[0])
    task = 'Create network resources'
    
    conn = psycopg2.connect(database=db, user=db_user, password=db_pwd, host=db_host,port=db_port)
    curs = conn.cursor()
    
    engine = create_engine(f"postgresql://{db_user}:{db_pwd}@{db_host}/{db}")
    db_contents = inspect(engine)
    if network_not_using_buffered_region:
        network_study_region = study_region
    else:
        network_study_region = buffered_study_region
    
    if not (db_contents.has_table('edges') and db_contents.has_table('nodes') and db_contents.has_table(intersections_table)):
        print("\nGet networks and save as graphs.")
        ox.settings.use_cache=True
        ox.settings.log_console=True
        if osmnx_retain_all == False:
            print(
                '''Note: "osmnx_retain_all = False" ie. only main network segment is retained. Please ensure this is appropriate for your study region (ie. networks on real islands may be excluded).'''
            ) 
        elif osmnx_retain_all == True:
            print(
                '''Note: "osmnx_retain_all = True" ie. all network segments will be retained. Please ensure this is appropriate for your study region (ie. networks on real islands will be included, however network artifacts resulting in isolated network segments, or network islands, may also exist.  These could be problematic if sample points are snapped to erroneous, mal-connected segments.  Check results.).'''
            ) 
        else:
            sys.exit("Please ensure the osmnx_retain_all has been defined for this region with values of either 'False' or 'True'")
        for network in ['all','pedestrian']:
            graphml = os.path.join(locale_dir,f'{network_study_region}_{network}_{osm_prefix}.graphml')
            if os.path.isfile(graphml):
                print(f'Network "{network}" for {network_study_region} has already been processed.')
                if network == 'pedestrian':
                    G = ox.load_graphml(graphml)
            else:
                print(f'Creating and saving {network} roads network... '),
                subtime = datetime.now()
                # load buffered study region in EPSG4326 from postgis
                sql = f'''SELECT geom_4326 AS geom FROM {network_study_region}'''
                
                polygon =  gpd.GeoDataFrame.from_postgis(sql, engine, geom_col='geom' )['geom'][0]
                if not network_polygon_iteration:
                    if network=='pedestrian':
                        G = ox.graph_from_polygon(polygon,  custom_filter= pedestrian, retain_all = osmnx_retain_all,network_type='walk')
                    else:
                        G = ox.graph_from_polygon(polygon,  network_type= 'all', retain_all = osmnx_retain_all)
                else:
                    # We allow for the possibility that multiple legitimate network islands may exist in this region (e.g. Hong Kong).
                    # These are accounted for by retrieving the network for each polygon in the buffered study region boundary, 
                    # and then taking the union of these using network compose if more than one network was retrieved.
                    N = list()
                    for poly in polygon:
                        if network=='pedestrian':
                            try:
                                N.append(ox.graph_from_polygon(poly,  custom_filter= pedestrian, retain_all = osmnx_retain_all,network_type='walk'))
                            except:
                                # if the polygon results in no return results from overpass, an error is thrown
                                pass
                        else:
                            try:
                                N.append(ox.graph_from_polygon(poly,  network_type= 'all', retain_all = osmnx_retain_all))
                            except:
                                # skip error
                                pass
                    
                    G = N[0]
                    if len(N) > 1:
                        for additional_network in N[1:]:
                            G = nx.compose(G,additional_network)
                    
                    
                    if type(network_connection_threshold)==int:
                        # A minimum total distance has been set for each induced network island; so, extract the node IDs of network components exceeding this threshold distance
                        # get all connected graph components, sorted by size
                        cc = sorted(nx.weakly_connected_components(G), key=len, reverse=True)
                        nodes = []
                        for c in cc:
                            if len(c) >= network_connection_threshold:
                                nodes.extend(c)
                        
                        nodes = set(nodes)
                        
                        # induce a subgraph on those nodes
                        G = nx.MultiDiGraph(G.subgraph(nodes))
                    
                ox.save_graphml(G,filepath=graphml,gephi=False)
                ox.save_graph_shapefile(G,filepath=graphml.strip('.graphml'))
                
            if network == 'pedestrian': 
                for feature in ['edges','nodes']:
                    if not db_contents.has_table(feature): 
                        print(f"\nCopy the pedestrian network {feature} from shapefiles to Postgis..."),
                        command = (
                                ' ogr2ogr -overwrite -progress -f "PostgreSQL" ' 
                               f' PG:"host={db_host} port={db_port} dbname={db}'
                               f' user={db_user} password={db_pwd}" '
                               f' {locale_dir}/{network_study_region}_{network}_{osm_prefix}/{feature}.shp '
                               f' -t_srs EPSG:{srid} '
                                ' -lco geometry_name="geom"' 
                                )
                        print(command)
                        sp.call(command, shell=True)
        if not db_contents.has_table(intersections_table): 
            ## Copy clean intersections to postgis
            print("\nPrepare and copy clean intersections to postgis... ")
            # Clean intersections
            G_proj = ox.project_graph(G)
            intersections = ox.consolidate_intersections(G_proj, tolerance=intersection_tolerance, rebuild_graph=False, dead_ends=False)
            intersections.crs = G_proj.graph['crs']
            intersections = intersections.to_crs(srid)
            # Copy to project Postgis database
            # Note: code written for Geopandas 0.7.0 which didn't have to_postgis implementation
            # the below code is used to simply copy projected coordinates to postgis, then construct geom
            df = pandas.DataFrame({'x':intersections.x, 'y':intersections.y})
            df.to_sql(intersections_table,engine,if_exists='replace')
            sql = f'''
            ALTER TABLE {intersections_table} ADD COLUMN geom geometry(Point, {srid});
            UPDATE {intersections_table} SET geom = ST_SetSRID(ST_MakePoint(x, y), {srid});
            CREATE INDEX {intersections_table}_gix ON {intersections_table} USING GIST (geom);
            '''
            with engine.begin() as connection:
                connection.execute(sql)   
            print("  - Done.")

        else:
            print("  - It appears that clean intersection data has already been prepared and imported for this region.")
    else:
        print("\nIt appears that edges and nodes have already been prepared and imported for this region.")
    
    curs.execute('''SELECT 1 WHERE to_regclass('public.edges_target_idx') IS NOT NULL;''')
    res = curs.fetchone()
    if res is None:
        print("\nCreate network topology...")
        sql = '''
        ALTER TABLE edges ADD COLUMN IF NOT EXISTS "source" INTEGER;
        ALTER TABLE edges ADD COLUMN IF NOT EXISTS "target" INTEGER;
        --SELECT pgr_createTopology('edges',0.0001,'geom','ogc_fid');
        '''
        with engine.begin() as connection:
            connection.execute(sql)   
        curs.execute("SELECT MIN(ogc_fid), MAX(ogc_fid) FROM edges;")
        min_id, max_id = curs.fetchone()
        print(f"there are {max_id - min_id + 1} edges to be processed")
        curs.close()
        
        interval = 10000
        for x in range(min_id, max_id+1, interval):
            curs = conn.cursor()
            curs.execute(
            f"select pgr_createTopology('edges', 1, 'geom', 'ogc_fid', rows_where:='ogc_fid>={x} and ogc_fid<{x+interval}');"
            )
            conn.commit()
            x_max = x + interval - 1
            if x_max > max_id:
                x_max = max_id
            print(f"edges {x} - {x_max} processed")
        
        sql = '''
        CREATE INDEX IF NOT EXISTS edges_source_idx ON edges("source");
        CREATE INDEX IF NOT EXISTS edges_target_idx ON edges("target");
        '''
        with engine.begin() as connection:
            connection.execute(sql)   
    else:
        print("  - It appears that the routable pedestrian network has already been set up for use by pgRouting.") 
    
    # ensure user is granted access to the newly created tables
    with engine.begin() as connection:
        connection.execute(grant_query)   
    
    script_running_log(script, task, start)
    
    # clean up
    conn.close()

if __name__ == '__main__':
    main()