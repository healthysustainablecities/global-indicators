"""
OpenStreetMap network setup.

Create pedestrian street networks for specified city.
"""

import os
import sys
import time
from datetime import datetime

import geopandas as gpd

# Set up project and region parameters for GHSCIC analyses
import ghsci
import networkx as nx
import osmnx as ox
from script_running_log import script_running_log
from sqlalchemy import text
from tqdm import tqdm


def osmnx_configuration(r):
    """Set up OSMnx for network retrieval and analysis, given a configured ghsci.Region (r)."""
    ox.settings.use_cache = True
    ox.settings.log_console = True
    # set OSMnx to retrieve filtered network to match OpenStreetMap publication date
    osm_publication_date = f"""[date:"{datetime.strptime(str(r.config['OpenStreetMap']['publication_date']), '%Y%m%d').strftime('%Y-%m-%d')}T00:00:00Z"]"""
    ox.settings.overpass_settings = (
        '[out:json][timeout:{timeout}]' + osm_publication_date + '{maxsize}'
    )
    if not r.config['network']['osmnx_retain_all']:
        print(
            """Note: "osmnx_retain_all = False" ie. only main network segment is retained. Please ensure this is appropriate for your study region (ie. networks on real islands may be excluded).""",
        )
    elif r.config['network']['osmnx_retain_all']:
        print(
            """Note: "osmnx_retain_all = True" ie. all network segments will be retained. Please ensure this is appropriate for your study region (ie. networks on real islands will be included, however network artifacts resulting in isolated network segments, or network islands, may also exist.  These could be problematic if sample points are snapped to erroneous, mal-connected segments.  Check results.).""",
        )
    else:
        sys.exit(
            "Please ensure the osmnx_retain_all has been defined for this region with values of either 'False' or 'True'",
        )


def generate_pedestrian_network_nodes_edges(r, pedestrian):
    """Generate pedestrian network using OSMnx and store in a PostGIS database, or otherwise retrieve it, given a configured ghsci.Region (r)."""
    if r.config['network']['buffered_region']:
        network_study_region = r.config['buffered_urban_study_region']
    else:
        network_study_region = r.codename
    if {'nodes', 'edges'}.issubset(r.tables):
        print(
            f'Network "pedestrian" for {network_study_region} has already been processed.',
        )
        print('\nLoading the pedestrian network.')
        nodes = r.get_gdf('nodes', index_col='osmid')
        edges = r.get_gdf('edges', index_col=['u', 'v', 'key'])
        G_proj = ox.graph_from_gdfs(nodes, edges, graph_attrs=None)
        return G_proj
    else:
        G = derive_pedestrian_network(r, network_study_region, pedestrian)
        print(
            '  - Save edges with geometry to postgis prior to simplification',
        )
        graph_to_postgis(
            G, r.engine, 'edges', nodes=False, geometry_name='geom_4326',
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
        G_proj = ox.project_graph(G, to_crs=r.config['crs']['srid'])
        if G_proj.is_directed():
            G_proj = G_proj.to_undirected()
        print(
            '  - Save simplified, projected, undirected graph edges and node GeoDataFrames to PostGIS',
        )
        graph_to_postgis(
            G_proj,
            r.engine,
            nodes_table='nodes',
            edges_table='edges_simplified',
        )
        return G_proj


def derive_pedestrian_network(
    r, network_study_region, pedestrian,
):
    """Derive routable pedestrian network using OSMnx."""
    print(
        'Creating and saving pedestrian roads network... ', end='', flush=True,
    )
    # load buffered study region in EPSG4326 from postgis
    sql = f"""SELECT ST_Transform(geom,4326) AS geom FROM {network_study_region}"""
    polygon = r.get_gdf(text(sql), geom_col='geom')['geom'][0]
    if not r.config['network']['polygon_iteration']:
        G = ox.graph_from_polygon(
            polygon,
            custom_filter=pedestrian,
            retain_all=r.config['network']['osmnx_retain_all'],
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
                        retain_all=r.config['network']['osmnx_retain_all'],
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

        if type(r.config['network']['connection_threshold']) == int:
            # A minimum total distance has been set for each induced network island; so, extract the node IDs of network components exceeding this threshold distance
            # get all connected graph components, sorted by size
            cc = sorted(
                nx.weakly_connected_components(G), key=len, reverse=True,
            )
            nodes = []
            for c in cc:
                if len(c) >= r.config['network']['connection_threshold']:
                    nodes.extend(c)

            nodes = set(nodes)

            # induce a subgraph on those nodes
            G = nx.MultiDiGraph(G.subgraph(nodes))

    G = G.to_undirected()
    print('Done.')
    return G


def graph_to_postgis(
    G,
    engine,
    nodes_table='nodes',
    edges_table='edges',
    nodes=True,
    edges=True,
    geometry_name='geom',
):
    """Save graph nodes and/or edges to postgis database."""
    if nodes is True and edges is False:
        nodes = ox.graph_to_gdfs(G, edges=False)
        gdf_to_postgis_format(nodes, engine, nodes_table, geometry_name)
    if edges is True and nodes is False:
        edges = ox.graph_to_gdfs(G, nodes=False)
        gdf_to_postgis_format(edges, engine, edges_table, geometry_name)
    else:
        nodes, edges = ox.graph_to_gdfs(G)
        gdf_to_postgis_format(nodes, engine, nodes_table, geometry_name)
        gdf_to_postgis_format(edges, engine, edges_table, geometry_name)


def gdf_to_postgis_format(gdf, engine, table, geometry_name='geom'):
    """Sets geometry with optional new name (e.g. 'geom') and writes to PostGIS, returning the reformatted GeoDataFrame."""
    gdf.columns = [
        geometry_name if x == 'geometry' else x for x in gdf.columns
    ]
    gdf = gdf.set_geometry(geometry_name)
    with engine.connect() as connection:
        gdf.to_postgis(
            table, connection, index=True, if_exists='replace',
        )


def load_intersections(r, G_proj):
    """Prepare intersections using a configured data source, or OSMnx to derive these, and store in postgis database."""
    if r.config['intersections_table'] not in r.tables:
        if (
            r.config['intersections_table']
            == f"intersections_osmnx_{r.config['network']['intersection_tolerance']}m"
        ):
            print(
                f"\nRepresent intersections using OpenStreetMap derived data using OSMnx consolidate intersections function with tolerance of {r.config['network']['intersection_tolerance']} metres... ",
            )
            intersections = ox.consolidate_intersections(
                G_proj,
                tolerance=r.config['network']['intersection_tolerance'],
                rebuild_graph=False,
                dead_ends=False,
            )
            intersections = gpd.GeoDataFrame(
                intersections, columns=['geom'],
            ).set_geometry('geom')
            with r.engine.connect() as connection:
                intersections.to_postgis(
                    r.config['intersections_table'], connection, index=True,
                )
        else:
            print(
                f"\nRepresent intersections using configured data {r.config['network']['intersections']['data']}... ",
            )
            r.ogr_to_db(
                source=f"/home/ghsci/process/data/{r.config['network']['intersections']['data']}",
                layer=r.config['intersections_table'],
            )
        print('  - Done.')
    else:
        print(
            'It appears that intersection data has already been prepared and imported for this region.',
        )


def create_pgrouting_network_topology(r):
    """Create network topology for pgrouting for later analysis of node relations for sample points."""
    sql = """SELECT 1 WHERE to_regclass('public.edges_target_idx') IS NOT NULL;"""
    with r.engine.begin() as connection:
        res = connection.execute(text(sql)).first()
    if res is None:
        print('\nCreate network topology...')
        sql = f"""
        ALTER TABLE edges ADD COLUMN IF NOT EXISTS "geom" geometry;
        UPDATE edges SET geom = ST_Transform(geom_4326, {r.config['crs']['srid']});
        ALTER TABLE edges ADD COLUMN IF NOT EXISTS "from" bigint;
        ALTER TABLE edges ADD COLUMN IF NOT EXISTS "to" bigint;
        UPDATE edges SET "from" = v, "to" = u WHERE key != 2;
        UPDATE edges SET "from" = u, "to" = v WHERE key = 2;
        ALTER TABLE edges ADD COLUMN IF NOT EXISTS "source" INTEGER;
        ALTER TABLE edges ADD COLUMN IF NOT EXISTS "target" INTEGER;
        ALTER TABLE edges ADD COLUMN IF NOT EXISTS "ogc_fid" SERIAL PRIMARY KEY;
        SELECT MIN(ogc_fid), MAX(ogc_fid) FROM edges;
        """
        with r.engine.begin() as connection:
            min_id, max_id = connection.execute(text(sql)).first()
        print(f'there are {max_id - min_id + 1} edges to be processed')
        interval = 10000
        for x in range(min_id, max_id + 1, interval):
            sql = f"select pgr_createTopology('edges', 1, 'geom', 'ogc_fid', rows_where:='ogc_fid>={x} and ogc_fid<{x+interval}');"
            with r.engine.begin() as connection:
                connection.execute(text(sql))
            x_max = x + interval - 1
            if x_max > max_id:
                x_max = max_id
            print(f'edges {x} - {x_max} processed')

        sql = """
        CREATE INDEX IF NOT EXISTS edges_source_idx ON edges("source");
        CREATE INDEX IF NOT EXISTS edges_target_idx ON edges("target");
        """
        with r.engine.begin() as connection:
            connection.execute(text(sql))
    else:
        print(
            '\nIt appears that the routable pedestrian network has already been set up for use by pgRouting.',
        )


def create_network_resources(codename):
    # simple timer for log file
    start = time.time()
    script = '_03_create_network_resources'
    task = 'Create network resources'
    r = ghsci.Region(codename)
    if {'edges', 'nodes', r.config['intersections_table']}.issubset(r.tables):
        print(
            '\nIt appears that edges, nodes and intersections have been prepared and imported for this region.',
        )
    else:
        osmnx_configuration(r)
        G_proj = generate_pedestrian_network_nodes_edges(
            r, ghsci.settings['network_analysis']['pedestrian'],
        )
        create_pgrouting_network_topology(r)
        load_intersections(r, G_proj)
        # ensure user is granted access to the newly created tables
        with r.engine.begin() as connection:
            connection.execute(text(ghsci.grant_query))

    # output to completion log
    script_running_log(r.config, script, task, start)
    r.engine.dispose()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    create_network_resources(codename)


if __name__ == '__main__':
    main()
