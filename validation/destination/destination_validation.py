import json

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd

import osmnx as ox

# configure script
cities = ['olomouc', 'belfast', 'sao_paulo']
indicators_filepath = './indicators.csv'
figure_filepath = './fig/destination-comparison-{city}.png'

def load_data(osm_buffer_gpkg_path, official_dests_filepath, dests_column_name):
    """
    Load the city destinations and study boundary.

    Parameters
    ----------
    osm_buffer_gpkg_path : str
        path to the buffered study area geopackage
    official_dests_filepath : str
        path to the official destinations shapefile
    dests_column_name : str
        XXX NEEDS TO BE ADDED XXX

    Returns
    -------
    XXX NEEDS TO BE ADDED XXX
    """

    # load the study area boundary as a shapely (multi)polygon
    gdf_study_area = gpd.read_file(osm_buffer_gpkg_path, layer='urban_study_region')
    study_area = gdf_study_area['geometry'].iloc[0]
    print(ox.ts(), 'loaded study area boundary')

    # load the official destinatinos shapefile
    gdf_official_destinations = gpd.read_file(official_dests_filepath)
    print(ox.ts(), 'loaded official destinations shapefile')

    # load the osm destinations shapefile
    gdf_osm = gpd.read_file(osm_buffer_gpkg_path, layer = 'destinations')
    gdf_osm_destinations = gdf_osm[gdf_osm['dest_name'] == dests_column_name]
    print(ox.ts(), 'loaded osm destinations shapefile')

	# Project the data to a common crs
    crs = gdf_study_area.crs
    if gdf_official_destinations.crs != crs:
        gdf_official_destinations = gdf_official_destinations.to_crs(crs)
        print(ox.ts(), 'projected official destinations')
    if gdf_osm_destinations.crs != crs:
        gdf_osm_destinations = gdf_osm_destinations.to_crs(crs)
        print(ox.ts(), 'projected osm destinations')

def total_destination_count(gdf_destinations):
    """
    Calculate the total count of destinations in gdf.

    Parameters
    ----------
    gdf_destinations : geopandas.GeoDataFrame
        the osm or official destinations

    Returns
    -------
    destinations_count : XXX
    """
    destinations_count = len(gdf_destinations)
    return destinations_count

def calculate_instersections(a, b):
	"""
    Calculate number of destinations that intersect in gdf.

    Parameters
    ----------
    a : geopandas.GeoDataFrame
        	the osm or official destinations
    b : geopandas.GeoDataFrame
    	 the osm or official destinations

    Returns
    -------
    intersections_count, percent_intersections_count : tuple
    """
	intersections = a['geometry'].intersects(b['geometry'].unary_union)
	intersections_count = len(a[intersections])
	percent_intersections_count = (intersections_count * 100) / len(a)
	return intersections_count, percent_intersections_count

def calculate_overlap(a, b, dist):
#gdf_osm ['geometry'] = A OR B
#gdf_official ['geometry'] = A OR B

	# buffer each by the current distance
	a_buff = a.buffer(dist)
	b_buff = b.buffer(dist)

    # take the unary union of each's buffered geometry
    a_buff_unary = a_buff.unary_union
    b_buff_unary = b_buff.unary_union

    # find the portion of each's buffered geometry that intersects with the other's buffered geometry
    a_buff_overlap = a_buff_unary.intersection(b_buff_unary)
    b_buff_overlap = b_buff_unary.intersection(a_buff_unary)

def min_distance(a, b):
	nearest_distances = []
	for destination in a:
		nearest_distance = b.distance(destination).min()
		nearest_distances.append(nearest_distance)
	a('nearest_distance') = nearest_distances
