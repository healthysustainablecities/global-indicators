"""
OpenStreetMap network setup.

Create pedestrian street networks for specified city.
"""

import os
import subprocess as sp
import sys
import time
from datetime import datetime

import geopandas as gpd
import networkx as nx
import osmnx as ox

# Set up project and region parameters for GHSCIC analyses
from _project_setup import *
from geoalchemy2 import Geometry, WKTElement
from script_running_log import script_running_log
from shapely.geometry import MultiPolygon, Polygon, shape
from sqlalchemy import create_engine, inspect, text
from tqdm import tqdm


def osmnx_configuration(region_config, network):
    """Set up OSMnx for network retrieval and analysis, including check of configuration."""
    ox.settings.use_cache = True
    ox.settings.log_console = True
    # set OSMnx to retrieve filtered network to match OpenStreetMap publication date
    osm_publication_date = f"""[date:"{datetime.strptime(str(region_config['OpenStreetMap']['publication_date']), '%Y%m%d').strftime('%Y-%m-%d')}T00:00:00Z"]"""
    ox.settings.overpass_settings = (
        '[out:json][timeout:{timeout}]' + osm_publication_date + '{maxsize}'
    )
    if not network['osmnx_retain_all']:
        print(
            """Note: "osmnx_retain_all = False" ie. only main network segment is retained. Please ensure this is appropriate for your study region (ie. networks on real islands may be excluded).""",
        )
    elif network['osmnx_retain_all']:
        print(
            """Note: "osmnx_retain_all = True" ie. all network segments will be retained. Please ensure this is appropriate for your study region (ie. networks on real islands will be included, however network artifacts resulting in isolated network segments, or network islands, may also exist.  These could be problematic if sample points are snapped to erroneous, mal-connected segments.  Check results.).""",
        )
    else:
        sys.exit(
            "Please ensure the osmnx_retain_all has been defined for this region with values of either 'False' or 'True'",
        )


def generate_pedestrian_network(engine, network, network_study_region, crs):
    """Generate pedestrian network using OSMnx and store in a PostGIS database, or otherwise retrieve it."""
    if db_contents.has_table('nodes') and db_contents.has_table('edges'):
        print(
            f'Network "pedestrian" for {network_study_region} has already been processed.',
        )
        print('\nLoading the pedestrian network.')
        with engine.connect() as connection:
            nodes = gpd.read_postgis('nodes', connection, index_col='osmid')
        with engine.connect() as connection:
            edges = gpd.read_postgis(
                'edges', connection, index_col=['u', 'v', 'key'],
            )
        G_proj = ox.graph_from_gdfs(nodes, edges, graph_attrs=None)
    else:
        G = derive_pedestrian_network(
            engine,
            network_study_region,
            network['osmnx_retain_all'],
            network['polygon_iteration'],
        )
        print('  - Remove unnecessary key data from edges')
        att_list = {
            k
            for n in G.edges
            for k in G.edges[n].keys()
            if k not in ['osmid', 'length']
        }
        capture_output = [
            [d.pop(att, None) for att in att_list]
            for n1, n2, d in tqdm(G.edges(data=True), desc=' ' * 18)
        ]
        del capture_output
        print('  - Project graph')
        G_proj = ox.project_graph(G, to_crs=crs['srid'])
        if G_proj.is_directed():
            G_proj = G_proj.to_undirected()
        print(
            '  - Save projected graph edges and node GeoDataFrames to PostGIS',
        )
        nodes, edges = ox.graph_to_gdfs(G_proj)
        gdf_to_postgis_format(nodes, engine, 'nodes')
        gdf_to_postgis_format(edges, engine, 'edges')


def derive_pedestrian_network(
    engine, network_study_region, osmnx_retain_all, network_polygon_iteration,
):
    """Derive routable pedestrian network using OSMnx."""
    print(
        'Creating and saving pedestrian roads network... ', end='', flush=True,
    )
    # load buffered study region in EPSG4326 from postgis
    sql = f"""SELECT ST_Transform(geom,4326) AS geom FROM {network_study_region}"""
    with engine.begin() as connection:
        polygon = gpd.GeoDataFrame.from_postgis(
            text(sql), connection, geom_col='geom',
        )['geom'][0]
    if not network_polygon_iteration:
        G = ox.graph_from_polygon(
            polygon,
            custom_filter=pedestrian,
            retain_all=osmnx_retain_all,
            network_type='walk',
        )
    else:
        # We allow for the possibility that multiple legitimate network islands may exist in this region (e.g. Hong Kong).
        # These are accounted for by retrieving the network for each polygon in the buffered study region boundary,
        # and then taking the union of these using network compose if more than one network was retrieved.
        N = list()
        for poly in polygon:
            try:
                N.append(
                    ox.graph_from_polygon(
                        poly,
                        custom_filter=pedestrian,
                        retain_all=osmnx_retain_all,
                        network_type='walk',
                    ),
                )
            except (ValueError, TypeError):
                # if the polygon results in no return results from overpass, an error is thrown
                pass

        G = N[0]
        if len(N) > 1:
            for additional_network in N[1:]:
                G = nx.compose(G, additional_network)

        if type(network['connection_threshold']) == int:
            # A minimum total distance has been set for each induced network island; so, extract the node IDs of network components exceeding this threshold distance
            # get all connected graph components, sorted by size
            cc = sorted(
                nx.weakly_connected_components(G), key=len, reverse=True,
            )
            nodes = []
            for c in cc:
                if len(c) >= network['connection_threshold']:
                    nodes.extend(c)

            nodes = set(nodes)

            # induce a subgraph on those nodes
            G = nx.MultiDiGraph(G.subgraph(nodes))

    print('Done.')
    return G


def gdf_to_postgis_format(gdf, engine, table, rename_geometry='geom'):
    """Sets geometry with optional new name (e.g. 'geom') and writes to PostGIS, returning the reformatted GeoDataFrame."""
    gdf.columns = [
        rename_geometry if x == 'geometry' else x for x in gdf.columns
    ]
    gdf = gdf.set_geometry(rename_geometry)
    with engine.connect() as connection:
        gdf.to_postgis(
            table, connection, index=True,
        )


def clean_intersections(engine, G_proj, network, intersections_table):
    """Generate cleaned intersections using OSMnx and store in postgis database, or otherwise retrieve them."""
    db_contents = inspect(engine)
    if not db_contents.has_table(intersections_table):
        ## Copy clean intersections to postgis
        print('\nPrepare and copy clean intersections to postgis... ')
        # Clean intersections
        intersections = ox.consolidate_intersections(
            G_proj,
            tolerance=network['intersection_tolerance'],
            rebuild_graph=False,
            dead_ends=False,
        )
        intersections = gpd.GeoDataFrame(
            intersections, columns=['geom'],
        ).set_geometry('geom')
        with engine.connect() as connection:
            intersections.to_postgis(
                intersections_table, connection, index=True,
            )
        print('  - Done.')

    else:
        print(
            '  - It appears that clean intersection data has already been prepared and imported for this region.',
        )


def create_pgrouting_network_topology(engine):
    """Create network topology for pgrouting for later analysis of node relations for sample points."""
    sql = """SELECT 1 WHERE to_regclass('public.edges_target_idx') IS NOT NULL;"""
    with engine.begin() as connection:
        res = connection.execute(text(sql)).first()
    if res is None:
        print('\nCreate network topology...')
        sql = """
        ALTER TABLE edges ADD COLUMN IF NOT EXISTS "from" bigint;
        ALTER TABLE edges ADD COLUMN IF NOT EXISTS "to" bigint;
        UPDATE edges SET "from" = v, "to" = u WHERE key != 2;
        UPDATE edges SET "from" = u, "to" = v WHERE key = 2;
        ALTER TABLE edges ADD COLUMN IF NOT EXISTS "source" INTEGER;
        ALTER TABLE edges ADD COLUMN IF NOT EXISTS "target" INTEGER;
        ALTER TABLE edges ADD COLUMN IF NOT EXISTS "ogc_fid" SERIAL PRIMARY KEY;
        SELECT MIN(ogc_fid), MAX(ogc_fid) FROM edges;
        """
        with engine.begin() as connection:
            min_id, max_id = connection.execute(text(sql)).first()
        print(f'there are {max_id - min_id + 1} edges to be processed')
        interval = 10000
        for x in range(min_id, max_id + 1, interval):
            sql = f"select pgr_createTopology('edges', 1, 'geom', 'ogc_fid', rows_where:='ogc_fid>={x} and ogc_fid<{x+interval}');"
            with engine.begin() as connection:
                connection.execute(text(sql))
            x_max = x + interval - 1
            if x_max > max_id:
                x_max = max_id
            print(f'edges {x} - {x_max} processed')

        sql = """
        CREATE INDEX IF NOT EXISTS edges_source_idx ON edges("source");
        CREATE INDEX IF NOT EXISTS edges_target_idx ON edges("target");
        """
        with engine.begin() as connection:
            connection.execute(text(sql))
    else:
        print(
            '  - It appears that the routable pedestrian network has already been set up for use by pgRouting.',
        )


def main():
    # simple timer for log file
    start = time.time()
    script = os.path.basename(sys.argv[0])
    task = 'Create network resources'
    engine = create_engine(
        f'postgresql://{db_user}:{db_pwd}@{db_host}/{db}',
        future=True,
        pool_pre_ping=True,
        connect_args={
            'keepalives': 1,
            'keepalives_idle': 30,
            'keepalives_interval': 10,
            'keepalives_count': 5,
        },
    )
    db_contents = inspect(engine)
    if network['buffered_region']:
        network_study_region = buffered_urban_study_region
    else:
        network_study_region = study_region

    if not (
        db_contents.has_table('edges')
        and db_contents.has_table('nodes')
        and db_contents.has_table(intersections_table)
    ):
        osmnx_configuration(region_config, network)
        generate_pedestrian_network(engine, network, network_study_region, crs)
        clean_intersections(engine, G_proj, network, intersections_table)
    else:
        print(
            '\nIt appears that edges and nodes have already been prepared and imported for this region.',
        )

    create_pgrouting_network_topology(engine)

    # ensure user is granted access to the newly created tables
    with engine.begin() as connection:
        connection.execute(text(grant_query))

    script_running_log(script, task, start)


if __name__ == '__main__':
    main()
