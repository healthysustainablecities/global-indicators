import json

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd

import osmnx as ox

# configure script
cities = ['olomouc', 'belfast', 'sao_paulo']
edge_buffer_dists = [0, 10, 50]
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
        name of columns that will be searched for in destination date

    Returns
    -------
    study_area, gdf_official_destinations, gdf_osm_destinations : tuple
    	the polygon composed of square kilometers that is the city's study area, 
    	the destinations from the official data source,
    	the destinations sourced from OSM
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
    
    # double-check everything has same CRS, then return
    assert gdf_study_area.crs == gdf_official_destinations.crs == gdf_osm_destinations.crs
    return study_area, gdf_official_destinations, gdf_osm_destinations

def total_destination_count(gdf_destinations):
    """
    Calculate the total count of destinations in gdf.

    Parameters
    ----------
    gdf_destinations : geopandas.GeoDataFrame
        the osm or official destinations 
        input either gdf_official_destinations or gdf_osm_destinations

    Returns
    -------
    destinations_count : value
    	the value of the number of destinations contained in the gdf
    """
    destinations_count = len(gdf_destinations)
    return destinations_count

def calculate_intersect(a, b, dist):
    """
    Calculate XXX. 

    Parameters
    ----------
    a : geopandas.GeoDataFrame
        the osm or offical destinations
    b : geopandas.GeoDataFrame
        the osm or offical destinations
    dist : int
        buffer distance in meters

    Returns
    -------
    intersections_count, percent_intersections, a_buff_overlap_count, b_buff_overlap_count
    	the count of intersections between the two gdf's, 
    	calculate the percentage of destinations that intersect, 
    	count of desitinations that overlap with gdf a
    	count of destiinations that overlap with gdf b
    """

	# focus on the geography of each gdf
	a_geography = a['geometry']
	b_geography = b['geometry']

	# calculate number of destinations that intersect in gdf
	intersections = a_geography.intersects(b_geography.unary_union)
	intersections_count = len(a[intersections])
	percent_intersections = (intersections_count * 100) / len(a)

	# buffer each by the current distance
	a_buff = a_geography.buffer(dist)
	b_buff = b_geography.buffer(dist)

    # take the unary union of each's buffered geometry
    a_buff_unary = a_buff.unary_union
    b_buff_unary = b_buff.unary_union

    # find the portion of each's buffered geometry that intersects with the other's buffered geometry
    a_buff_overlap_count = a_buff_unary.intersection(b_buff_unary)
    b_buff_overlap_count = b_buff_unary.intersection(a_buff_unary)

    return intersections_count, percent_intersections, a_buff_overlap_count, b_buff_overlap_count

def min_distance(a, b):
    """
    Load the city destinations and study boundary.

    Parameters
    ----------
    a : geopandas.GeoDataFrame
        the osm or offical destinations
    b : geopandas.GeoDataFrame
        the osm or offical destinations

    Returns
    -------
    XXX NEEDS TO BE ADDED XXX
    """

	nearest_distances = []
	for destination in a:
		nearest_distance = b.distance(destination).min()
		nearest_distances.append(nearest_distance)
	a('nearest_distance') = nearest_distances

# RUN THE SCRIPT
indicators = {}
for city in cities:

    print(ox.ts(), f'begin processing {city}')
    indicators[city] = {}

    # load this city's configs
    with open(f'../configuration/{city}.json') as f:
        config = json.load(f)

    # load street gdfs from osm graph and official shapefile, then clip to study area boundary polygon
    gdf_osm_streets, gdf_official_streets, study_area = load_data(config['osm_graphml_path'],
                                                                  config['osm_buffer_gpkg_path'],
                                                                  config['official_streets_shp_path'])

    # plot map of study area + osm and official streets, save to disk
    fp = figure_filepath.format(city=city)
    fig, ax = plot_data(gdf_osm_streets, gdf_official_streets, study_area, fp)

    # calculate total street length and edge count in each dataset, then add to indicators
    osm_total_length, osm_edge_count = total_edge_length_count(gdf_osm_streets)
    official_total_length, official_edge_count = total_edge_length_count(gdf_official_streets)
    indicators[city]['osm_total_length'] = osm_total_length
    indicators[city]['osm_edge_count'] = osm_edge_count
    indicators[city]['official_total_length'] = official_total_length
    indicators[city]['official_edge_count'] = official_edge_count
    print(ox.ts(), 'calculated edge lengths and counts')

    # calculate the % overlaps of areas and lengths between osm and official streets with different buffer distances
    for dist in edge_buffer_dists:
        osm_area_pct, official_area_pct, osm_length_pct, official_length_pct = calculate_overlap(gdf_osm_streets, gdf_official_streets, dist)
        indicators[city][f'osm_area_pct_{dist}'] = osm_area_pct
        indicators[city][f'official_area_pct_{dist}'] = official_area_pct
        indicators[city][f'osm_length_pct_{dist}'] = osm_length_pct
        indicators[city][f'official_length_pct_{dist}'] = official_length_pct
        print(ox.ts(), f'calculated area/length of overlaps for buffer {dist}')

# turn indicators into a dataframe and save to disk
df_ind = pd.DataFrame(indicators).T
df_ind.to_csv(indicators_filepath, index=True, encoding='utf-8')
print(ox.ts(), f'all done, saved indicators to disk at "{indicators_filepath}"')

