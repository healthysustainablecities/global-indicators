import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.patches import RegularPolygon
import shapely
from shapely.geometry import Polygon
from matplotlib.patches import RegularPolygon
import json
import osmnx as ox


def load_data(osm_buffer_gpkg_path, official_dests_filepath):

    # load the study area boundary as a shapely (multi)polygon
    gdf_study_area = gpd.read_file(osm_buffer_gpkg_path, layer='urban_study_region')
    study_area = gdf_study_area['geometry']

    # load the official destinatinos shapefile
    gdf_official_destinations = gpd.read_file(official_dests_filepath)

    # load the osm destinations shapefile
    gdf_osm = gpd.read_file(osm_buffer_gpkg_path, layer = 'destinations')
    gdf_osm_destinations = gdf_osm[gdf_osm['dest_name'] == 'fresh_food_market']
  
    return study_area, gdf_official_destinations, gdf_osm_destinations


def hex_plot(geo_pkg_path, gdf_osm_destinations, gdf_official_destinations):

    city = gpd.read_file(geo_pkg_path, layer='urban_study_region')
    city = city['geometry']
    city.plot(alpha=0.5,figsize=(20,60),edgecolor='black')

    xmin,ymin,xmax,ymax = city.total_bounds # lat-long of 2 corners
    xmin -= 500
    xmax += 500
    ymin -= 500
    ymax += 500
    # East-West extent of urban_study_region
    EW = (xmax - xmin)
    # North-South extent of urban_study_region
    NS = (ymax - ymin)
    # Hexagon bins diameter should equal 500 meters
    d = 500
    # horizontal width of hexagon = w = d* sin(60)
    w = d*np.sin(np.pi/3)
    # Approximate number of hexagons per row = EW/w
    n_cols = int(EW/d)+ 1
    # Approximate number of hexagons per column = NS/d
    n_rows = int(NS/w)+ 1

    ax = city.boundary.plot(edgecolor='black',figsize=(20,60))
    w = (xmax-xmin)/n_cols # width of hexagon
    d = w/np.sin(np.pi/3) #diameter of hexagon 500 meters
    array_of_hexes = []
    # +1 added to n_rows since the range function runs from 0 through (n-1), and the number of rows of hexgons plotted
    # was one less than the expcted number of rows.
    for rows in range(0,n_rows + 1):
        hcoord = np.arange(xmin, xmax, w) + (rows % 2) * w/2
        vcoord = [ymax- rows*d*0.75] * n_cols
        for x, y in zip(hcoord, vcoord):
            hexes = RegularPolygon((x, y), numVertices=6, radius=d/2, alpha=0.2, edgecolor='k')
            verts = hexes.get_path().vertices
            trans = hexes.get_patch_transform()
            points = trans.transform(verts)
            array_of_hexes.append(Polygon(points))
            ax.add_patch(hexes)
    # Set the height and width of the plot to be greater than the urban_study_region
    ax.set_xlim([xmin - 500, xmax+ 500])
    ax.set_ylim([ymin - 500, ymax+ 500])
    plt.show()

    # Plot the city boundary, hex_grid layer, osm points layer and official points layer
    hex_grid = gpd.GeoDataFrame({'geometry': array_of_hexes})
    fig, ax = plt.subplots(figsize=(20, 60))
    city.boundary.plot(ax=ax, edgecolor='black', figsize=(20, 60))
    hex_grid.plot(ax=ax, alpha=0.7, color="black")
    gdf_osm_destinations.plot(ax=ax, color="black", edgecolor='black')
    gdf_official_destinations.plot(ax=ax, color="black", edgecolor='black')

    # Find clipped hexagon layer to later determine if points are present in each hexagon within the study region
    city_df = gpd.GeoDataFrame(city)
    hex_grid_clipped = gpd.overlay(hex_grid, city_df)
    hex_grid_clipped = gpd.GeoDataFrame(hex_grid_clipped, geometry='geometry')
    hex_grid_clipped.plot(figsize=(20, 60))

    return hex_grid, hex_grid_clipped


def determine_points_in_hexagon_bin(hex_grid_clipped, gdf_osm_destinations, gdf_official_destinations):
    result_rows = []
    osm_layer_df = gpd.GeoDataFrame(gdf_osm_destinations)
    official_layer_df = gpd.GeoDataFrame(gdf_official_destinations)
    # Loop through hexagon bins
    for idx, hexagon in enumerate(hex_grid_clipped['geometry']):
        osm_count = 0
        official_count = 0
        total_count = 0
        # Loop through OSM Points
        for row in osm_layer_df.iterrows():
            layer_point = row[1]['geometry']
            if hexagon.contains(layer_point):
                osm_count += 1
                total_count += 1
        # Loop through Official Points
        for row in official_layer_df.iterrows():
            layer_point = row[1]['geometry']
            if hexagon.contains(layer_point):
                official_count += 1
                total_count += 1

        osm_count_bool = "YES" if osm_count else "NO"
        official_count_bool = "YES" if official_count else "NO"
        total_count_bool = "YES" if total_count else "NO"
        percentage_osm = osm_count / total_count if total_count else 0
        percentage_official = official_count / total_count if total_count else 0
        weight = True if bool(osm_count) == bool(official_count) else False
        result_rows.append([idx, total_count_bool, total_count, osm_count_bool, osm_count, percentage_osm,
                            official_count_bool, official_count, percentage_official, weight])

    result_df = pd.DataFrame(result_rows, columns=["Hexagon Index", "Contains Points", "Number of Points",
                                                   "Contains OSM Points", "Number of OSM Points", "Hex OSM Perecentage",
                                                   "Contains Official Points", "Number of Official Points",
                                                   "Hex Official Perecentage", "Weight"])
    return result_df
