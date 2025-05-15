"""
Identify large public urban green space (LPUGS) through use of the Google Earth Engine API
"""
import sys
import time

# Import Earth Engine and Google Earth Engine Map libraries
import ee
import geemap
import psycopg2
import geopandas as gpd
import pandas as pd
import osmnx as ox
import networkx as nx
from shapely.geometry import Point, LineString, shape
from shapely.ops import substring

# import getpass
from script_running_log import script_running_log
from sqlalchemy import text

import ghsci


def fetch_lpugs_availability_data_as_gdf(r: ghsci.Region) -> tuple:
    """Fetch urban study region and AOS public OSM data as GeoDataFrames."""
    # Fetch urban study region data
    with r.engine.connect() as connection:
        urban_study_region_gdf = gpd.read_postgis(
            """
            SELECT ST_Transform(geom, 4326) AS geom
            FROM urban_study_region;
            """,
            connection,
            geom_col='geom',
        )
        
    # Fetch AOS public OSM data
    with r.engine.connect() as connection:
        aos_public_osm_gdf = gpd.read_postgis(
            """
            SELECT ST_Transform(geom, 4326) AS geom, aos_id, aos_ha_public
            FROM aos_public_osm;
            """,
            connection,
            geom_col='geom',
        )
        
    return urban_study_region_gdf, aos_public_osm_gdf


def fetch_lpugs_accessibility_data_as_gdf(r: ghsci.Region) -> tuple:
    """Fetch network and population grid as GeoDataFrames with unique IDs added."""
    # Fetch network nodes data and add unique ID
    with r.engine.connect() as connection:
        network_nodes_gdf = gpd.read_postgis(
            """
            SELECT ST_Transform(geom, 4326) AS geom, 
                   osmid, 
                   y AS lat, 
                   x AS lon
            FROM nodes;
            """,
            connection,
            geom_col='geom',
        )
        network_nodes_gdf = network_nodes_gdf.rename(columns={'lat': 'y', 'lon': 'x'})

    # Fetch network edges data and add unique ID
    with r.engine.connect() as connection:
        network_edges_gdf = gpd.read_postgis(
            """
            SELECT 
                geom_4326 AS geom,
                u, 
                v, 
                key, 
                length, 
                osmid,
                source,
                target
            FROM edges;
            """,
            connection,
            geom_col='geom',
        )
        network_edges_gdf.set_index(['u', 'v', 'key'], inplace=True)

    # Fetch population grid data
    with r.engine.connect() as connection:
        population_grid_gdf = gpd.read_postgis(
            f"""
            SELECT ST_Transform(geom, 4326) AS geom, grid_id, pop_est
            FROM {r.config["population_grid"]};
            """,
            connection,
            geom_col='geom',
        )
        
    return network_nodes_gdf, network_edges_gdf, population_grid_gdf
        

def generate_and_upload_lpugs(r):
    """Generate LPUGS data and upload it directly to the database using SQL queries."""
    # Fetch data for the region
    urban_study_region_gdf, aos_public_osm_gdf = fetch_lpugs_availability_data_as_gdf(r)
    
    # Initialize Google Earth Engine
    project_id = r.config['gee_project_id']
    ee.Initialize(project=project_id)

    # Convert GeoDataFrames to Earth Engine FeatureCollections
    urban_study_region_fc = geemap.gdf_to_ee(urban_study_region_gdf, geodesic=False)
    aos_public_osm_fc = geemap.gdf_to_ee(aos_public_osm_gdf, geodesic=False)
    
    # Filter AOS features larger than 1 hectare
    aos_public_osm_filtered_1ha = aos_public_osm_fc.filter(ee.Filter.gte('aos_ha_public', 1))
    
    # Define the target year and date range
    target_year = r.config['year']
    start_date = f"{target_year}-01-01"
    end_date = f"{target_year + 1}-01-01"

    # Get the bounding box of the study region
    bounding_box = urban_study_region_fc.geometry().bounds()
    
    # Function to mask clouds in Sentinel-2 imagery
    def mask_s2_clouds(image):
        qa = image.select('QA60')
        cloud_mask = 1 << 10
        cirrus_mask = 1 << 11
        mask = qa.bitwiseAnd(cloud_mask).eq(0).And(qa.bitwiseAnd(cirrus_mask).eq(0))
        return image.updateMask(mask).divide(10000).select(["B.*"]).copyProperties(image, ["system:time_start"])

    # Function to calculate NDVI
    def calculate_ndvi(image):
        ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
        return image.addBands(ndvi)
    
    # Load Sentinel-2 imagery, mask clouds, and calculate NDVI
    sentinel_collection = ee.ImageCollection('COPERNICUS/S2_HARMONIZED') \
        .filterBounds(bounding_box) \
        .filterDate(start_date, end_date) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 90)) \
        .map(mask_s2_clouds) \
        .map(calculate_ndvi)
    
    # Calculate annual average NDVI
    annual_average_ndvi = sentinel_collection.select('NDVI').mean().clip(aos_public_osm_filtered_1ha)
    
    # Create a mask for LPUGS (NDVI >= 0.2)
    lpugs_mask = annual_average_ndvi.gte(0.2).rename('LPUGS')
    
    # Function to add NDVI mean to each feature
    def add_ndvi_to_feature(feature):
        ndvi_value = annual_average_ndvi.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=feature.geometry(),
            scale=10
        ).get('NDVI')
        return feature.set({'NDVI_mean': ndvi_value})

    # Function to calculate LPUGS area in hectares
    def calculate_ndvi_area(feature):
        ndvi_area = lpugs_mask.multiply(ee.Image.pixelArea()).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=feature.geometry(),
            scale=10
        ).get('LPUGS')
        return feature.set({'NDVI_ha': ee.Number(ndvi_area).divide(1e4)})

    # Apply NDVI and area calculations to filtered AOS features
    lpugs_fc = aos_public_osm_filtered_1ha.map(add_ndvi_to_feature).map(calculate_ndvi_area)
    lpugs_filtered = lpugs_fc.filter(ee.Filter.gte('NDVI_mean', 0.2))
    
    # Convert Feature Collection to GeoPandas Data Frame
    lpugs_gdf = geemap.ee_to_gdf(lpugs_filtered)
       
    # Convert geometry to WKT
    lpugs_gdf['geom'] = lpugs_gdf['geometry'].apply(lambda x: x.wkt)
    
    # Extract int from crs
    crs_metric = r.config['crs_srid']
    srid_int = int(crs_metric.split(':')[1])

    # Define SQL queries for LPUGS and LPUGS nodes with the metric SRID
    with r.engine.begin() as connection:
        # Drop and create LPUGS table
        connection.execute(text("""
            DROP TABLE IF EXISTS large_public_urban_green_space;
            CREATE TABLE large_public_urban_green_space (
                lpugs_id SERIAL PRIMARY KEY,
                aos_id INTEGER,
                aos_ha_public FLOAT,
                NDVI_mean FLOAT,
                NDVI_ha FLOAT,
                geom GEOMETRY(Geometry, %s)
            );
        """ % srid_int))
        
        # Insert data row by row into LPUGS table
        insert_data_sql = """
        INSERT INTO large_public_urban_green_space (aos_id, aos_ha_public, NDVI_mean, NDVI_ha, geom)
        VALUES (:aos_id, :aos_ha_public, :NDVI_mean, :NDVI_ha, ST_Transform(ST_SetSRID(ST_GeomFromText(:geom), 4326), :target_srid));
        """
        
        for _, row in lpugs_gdf.iterrows():
            connection.execute(
                text(insert_data_sql),
                {
                    'aos_id': row['aos_id'],
                    'aos_ha_public': row['aos_ha_public'],
                    'NDVI_mean': row['NDVI_mean'],
                    'NDVI_ha': row['NDVI_ha'],
                    'geom': row['geom'],
                    'target_srid': srid_int
                }
            )
        
        # Create the lpugs_nodes_30m_line table
        connection.execute(text("""
            DROP TABLE IF EXISTS lpugs_nodes_30m_line;
            CREATE TABLE lpugs_nodes_30m_line AS
            SELECT DISTINCT n.*, l.lpugs_id
            FROM aos_public_any_nodes_30m_line n
            JOIN large_public_urban_green_space l ON n.aos_id = l.aos_id;
            
            CREATE INDEX lpugs_nodes_30m_line_gix ON lpugs_nodes_30m_line USING GIST (geom);
        """))


def lpugs_accessibility(r):
    """Perform LPUGS accessibility network analysis and upload directly to the database."""
    # Fetch relevant data
    network_nodes_gdf, network_edges_gdf, population_grid_gdf = fetch_lpugs_accessibility_data_as_gdf(r)

    # Fetch LPUGS nodes (previously saved)
    with r.engine.connect() as connection:
        lpugs_nodes_gdf = gpd.read_postgis(
            """
            SELECT ST_Transform(geom, 4326) AS geom, aos_id, aos_entryid, node, lpugs_id
            FROM lpugs_nodes_30m_line;
            """,
            connection,
            geom_col='geom',
        )

    # Reproject all to metric CRS for distance calculations
    crs_metric = r.config['crs_srid']
    network_nodes_gdf = network_nodes_gdf.to_crs(crs_metric)
    network_edges_gdf = network_edges_gdf.to_crs(crs_metric)
    lpugs_nodes_gdf = lpugs_nodes_gdf.to_crs(crs_metric)
    population_grid_gdf = population_grid_gdf.to_crs(crs_metric)

    # Reconstruct a NetworkX MultiDiGraph using osmid as the primary identifier
    G = nx.MultiDiGraph()
    G.graph['crs'] = crs_metric

    # Add nodes with osmid as the primary reference
    for _, row in network_nodes_gdf.iterrows():
        # Create a Point geometry from lon/lat if geometry column doesn't exist
        if 'geometry' not in row:
            point = Point(row['x'], row['y'])
        else:
            point = row['geometry']
            
        G.add_node(
            row['osmid'],
            x=row['x'],
            y=row['y'],
            geometry=point
        )

    # Add edges with proper node references
    for (u, v, k), row in network_edges_gdf.iterrows():
        # Convert edge osmid to string representation if it's a list
        edge_osmid = str(row['osmid']) if isinstance(row['osmid'], list) else row['osmid']
        
        # Verify nodes exist first
        if u not in G.nodes or v not in G.nodes:
            print(f"Skipping edge - nodes not in graph: u={u}, v={v}")
            continue
            
        G.add_edge(
            u,
            v,
            key=k,
            length=row['length'],
            osmid=edge_osmid,
            geometry=row['geom']
        )

    # Convert to undirected graph for accessibility analysis
    G = ox.utils_graph.get_undirected(G)

    # Get nearest network node IDs for LPUGS points
    lpugs_node_ids = [
        ox.distance.nearest_nodes(G, point.x, point.y)
        for point in lpugs_nodes_gdf.geometry
    ]
    
    def trim_line_to_length(line: LineString, max_length: float) -> LineString:
        # Returns portion of the LineString up to the given length
        if line.length <= max_length:
            return line
        return substring(line, 0, max_length)

    # Compute all nodes within 500m network distance from LPUGS nodes
    trimmed_edges = []
    all_reachable_nodes = set()  # Track all nodes within 500m
    
    for node_id in lpugs_node_ids:
        try:
            dists, paths = nx.single_source_dijkstra(G, node_id, cutoff=500, weight='length')
            all_reachable_nodes.update(dists.keys())  # Add all reachable nodes
            
            for target_id, total_dist in dists.items():
                if target_id == node_id:
                    continue
                path = paths[target_id]
                accumulated = 0

                for u, v in zip(path[:-1], path[1:]):
                    edge_data = min(G.get_edge_data(u, v).values(), key=lambda d: d['length'])
                    edge_geom = edge_data['geometry']
                    edge_len = edge_data['length']

                    if accumulated + edge_len > 500:
                        remaining = 500 - accumulated
                        trimmed_geom = trim_line_to_length(edge_geom, remaining)
                        trimmed_edges.append({
                            'u': u,
                            'v': v,
                            'key': 0,
                            'length': remaining,
                            'osmid': edge_data.get('osmid'),
                            'geometry': trimmed_geom
                        })
                        break  # Stop at cutoff
                    else:
                        trimmed_edges.append({
                            'u': u,
                            'v': v,
                            'key': 0,
                            'length': edge_len,
                            'osmid': edge_data.get('osmid'),
                            'geometry': edge_geom
                        })
                        accumulated += edge_len

        except nx.NetworkXNoPath:
            continue

    # Create a subgraph with all edges that connect the reachable nodes
    G_sub = nx.MultiDiGraph(**G.graph)
    
    # Add all nodes in the reachable set
    G_sub.add_nodes_from((n, G.nodes[n]) for n in all_reachable_nodes)
    
    # Add all edges between these nodes
    for u, v, k, data in G.edges(data=True, keys=True):
        if u in all_reachable_nodes and v in all_reachable_nodes:
            G_sub.add_edge(u, v, key=k, **data)

    # If no nodes were found, create empty GeoDataFrames
    if len(G_sub.nodes) == 0:
        accessible_nodes_gdf = gpd.GeoDataFrame()
        accessible_edges_gdf = gpd.GeoDataFrame(columns=['u', 'v', 'key', 'length', 'osmid', 'geometry'])
    else:
        # Convert subgraph to GeoDataFrames
        accessible_nodes_gdf, accessible_edges_gdf = ox.graph_to_gdfs(
            G_sub, 
            nodes=True, 
            edges=True,
            node_geometry=True,
            fill_edge_geometry=True
        )
        # Reset the index to get u, v, key as columns
        accessible_edges_gdf = accessible_edges_gdf.reset_index()

    # Ensure we have the required columns in the edges GeoDataFrame
    required_columns = ['u', 'v', 'key', 'length', 'osmid', 'geometry']
    for col in required_columns:
        if col not in accessible_edges_gdf.columns:
            accessible_edges_gdf[col] = None

    # Rename population grid's 'geom' to 'geometry' for the spatial join
    population_grid_for_join = population_grid_gdf.rename_geometry('geometry')

    # Perform spatial join with the population grid
    lpugs_accessibility_grid = gpd.sjoin(
        population_grid_for_join[['grid_id', 'pop_est', 'geometry']],
        accessible_edges_gdf[['geometry']],
        how='inner',
        predicate='intersects'
    )

    # Keep only unique grid cells with their population
    lpugs_accessibility_grid = lpugs_accessibility_grid[
        ['grid_id', 'pop_est', 'geometry']
    ].drop_duplicates('grid_id')

    #Upload both layers to PostGIS in metric CRS
    
    # Extract int from crs
    srid_int = int(crs_metric.split(':')[1])
    
    with r.engine.begin() as connection:
        # Drop and create tables
        connection.execute(text("DROP TABLE IF EXISTS lpugs_accessible_network;"))
        connection.execute(text("DROP TABLE IF EXISTS lpugs_accessibility_grid;"))

        # Create and populate lpugs_accessible_network with metric CRS
        connection.execute(text(f"""
            CREATE TABLE lpugs_accessible_network (
                id SERIAL PRIMARY KEY,
                u INT8,
                v INT8,
                key INT8,
                length FLOAT,
                osmid TEXT,
                geom GEOMETRY(LineString, {srid_int})
            );
        """))

        if not accessible_edges_gdf.empty:
            # Ensure the edges are in the correct CRS (should already be)
            accessible_edges_gdf = accessible_edges_gdf.to_crs(srid_int)
            
            stmt = text(f"""
                INSERT INTO lpugs_accessible_network (u, v, key, length, osmid, geom)
                VALUES (:u, :v, :key, :length, :osmid, ST_SetSRID(ST_GeomFromText(:geom), {srid_int}));
            """)
            
            params = []
            for _, row in accessible_edges_gdf.iterrows():
                params.append({
                    'u': row['u'],
                    'v': row['v'],
                    'key': row['key'],
                    'length': row['length'],
                    'osmid': str(row['osmid']),
                    'geom': row['geometry'].wkt if row['geometry'] is not None else None
                })
            
            if params:
                connection.execute(stmt, params)

        # Create and populate lpugs_accessibility_grid with metric CRS
        connection.execute(text(f"""
            CREATE TABLE lpugs_accessibility_grid (
                grid_id TEXT PRIMARY KEY,
                pop_est FLOAT,
                geom GEOMETRY(Polygon, {srid_int})
            );
        """))

        if not lpugs_accessibility_grid.empty:
            # Ensure the grid is in the correct CRS (should already be)
            lpugs_accessibility_grid = lpugs_accessibility_grid.to_crs(srid_int)
            
            stmt = text(f"""
                INSERT INTO lpugs_accessibility_grid (grid_id, pop_est, geom)
                VALUES (:grid_id, :pop_est, ST_SetSRID(ST_GeomFromText(:geom), {srid_int}));
            """)
            
            params = [{
                'grid_id': row['grid_id'],
                'pop_est': row['pop_est'],
                'geom': row['geometry'].wkt
            } for _, row in lpugs_accessibility_grid.iterrows()]
            
            connection.execute(stmt, params)


def large_public_urban_green_space(codename):
    # simple timer for log file
    start = time.time()
    script = '_07_large_public_urban_green_space'
    task = 'Prepare Large Public Urban Green Spaces (LPUGS)'
    r = ghsci.Region(codename)
    generate_and_upload_lpugs(r)
    lpugs_accessibility(r)
    # output to completion log
    script_running_log(r.config, script, task, start)
    r.engine.dispose()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    large_public_urban_green_space(codename)


if __name__ == '__main__':
    main()