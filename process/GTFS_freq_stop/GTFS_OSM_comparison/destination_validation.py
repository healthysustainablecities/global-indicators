import json
import geopandas as gpd
import matplotlib.pyplot as plt
import os
import pandas as pd
from shapely.geometry import Polygon, LineString
import osmnx as ox
import numpy as np


def load_data(osm_buffer_gpkg_path, osm_dest_name, official_dests_filepath):#, destinations_column, destinations_values):
	"""
	Load the city destinations and study boundary.

	Parameters
	----------
	osm_buffer_gpkg_path : str
		path to the buffered study area geopackage
	osm_dest_name: str
		destination name to validate in osm gpkg
	official_dests_filepath : str
		path to the official destinations shapefile
	destinations_column : str
		column name containing categories of food-related destinations
	destinations_values : str
		acceptable values for categories of food-related destinations

	Returns
	-------
	study_area, geopackage, gdf_osm_destinations, gdf_official_destinations : tuple
		the polygon composed of square kilometers that is the city's study area,
		the OSM derived dataset
		the destinations sourced from OSM,
		the destinations from the official data sources
	"""

	# load the study area boundary as a shapely (multi)polygon
	gdf_study_area = gpd.read_file(osm_buffer_gpkg_path, layer='urban_study_region')
	study_area = gdf_study_area['geometry'].iloc[0]
	print(ox.ts(), 'loaded study area boundary')

	# load the entire geopackage
	geopackage = gpd.read_file(osm_buffer_gpkg_path)

	# load the official destinations shapefile
	# retain only rows with desired values in the destinations column
	gdf_official_destinations = gpd.read_file(official_dests_filepath)
	#mask = gdf_official_destinations[destinations_column].isin(destinations_values)
	#gdf_official_destinations = gdf_official_destinations[mask]
	print(ox.ts(), 'loaded and filtered official destinations shapefile')

	# load the osm destinations shapefile
	gdf_osm = gpd.read_file(osm_buffer_gpkg_path, layer = 'destinations')
	gdf_osm_destinations = gdf_osm[gdf_osm['dest_name'] == osm_dest_name]
	print(ox.ts(), 'loaded osm destinations shapefile')

	# project the data to a common crs
	crs = gdf_study_area.crs
	if geopackage.crs != crs:
		geopackage = geopackage.to_crs(crs)
		print(ox.ts(), 'projected geopackage')
	if gdf_official_destinations.crs != crs:
		gdf_official_destinations = gdf_official_destinations.to_crs(crs)
		print(ox.ts(), 'projected official destinations')
	if gdf_osm_destinations.crs != crs:
		gdf_osm_destinations = gdf_osm_destinations.to_crs(crs)
		print(ox.ts(), 'projected osm destinations')

	# spatially clip the destinationss to the study area boundary
	import warnings; warnings.filterwarnings('ignore', 'GeoSeries.notna', UserWarning)  # temp warning suppression
	gdf_osm_destinations_clipped = gpd.clip(gdf_osm_destinations, study_area)
	gdf_official_destinations_clipped = gpd.clip(gdf_official_destinations, study_area)
	print(ox.ts(), 'clipped osm/official destinations to study area boundary')

	# double-check everything has same CRS, then return
	assert gdf_study_area.crs == geopackage.crs == gdf_osm_destinations_clipped.crs == gdf_official_destinations_clipped.crs
	return study_area, geopackage, gdf_osm_destinations_clipped, gdf_official_destinations_clipped

def get_core_dests(geopackage, buff, study_area, dests):
	"""
	Create a negative buffered convex hull of destinations. This will get to the core of the destination data.

	Parameters
	----------
	geopackage : geopandas.GeoDataFrame
		the osm derived spatial data
	buff : int
		the what to multiply the smaller direction by to find urban core
	study_area : shapely.Polygon or shapely.MultiPolygon
		the study area boundary to negative-buffer
	dests : geopandas.GeoDataFrame
		the osm destinations or official destinations

	Returns
	-------
	dests_core
		destinations that fall within the core (negative-buffered) study area
	"""

	# Define the extents of the study area
	xmin,ymin,xmax,ymax = geopackage['geometry'].total_bounds
	x = xmax - xmin
	y = ymax - ymin

	if x < y:
		buffer_dist = buff * x
	else:
		buffer_dist = buff * y

	study_area_core = study_area.buffer(-buffer_dist)
	mask = dests.within(study_area_core)
	dests_core = dests[mask]
	return dests_core

def plot_city_data(gdf_osm_destinations_clipped, gdf_official_destinations_clipped, study_area, filepath, figsize=(10, 10), bgcolor='#333333', projected=True):
	"""
	Plot the OSM vs official destinations and save to disk.

	Parameters
	----------
	gdf_osm_destinations_clipped : geopandas.GeoDataFrame
		the osm destinations
	gdf_official_destinations_clipped : geopandas.GeoDataFrame
		the official destinations
	study_area : shapely.Polygon or shapely.MultiPolygon
		the study area boundary
	filepath : str
		path to save figure as file
	figsize : tuple
		size of plotting figure
	bgcolor : str
		background color of plot
	projected : bool
		True if gdfs are projected rather than lat-lng

	Returns
	-------
	fig, ax : tuple
	"""

	fig, ax = plt.subplots(figsize=figsize, facecolor=bgcolor)
	ax.set_facecolor(bgcolor)

	# turn study_area polygon into gdf with correct CRS
	gdf_boundary = gpd.GeoDataFrame(geometry=[study_area], crs=gdf_osm_destinations_clipped.crs)

	# plot study area, then official destinations, then osm destinations as layers
	_ = gdf_boundary.plot(ax=ax, facecolor='k', label='Study Area')
	_ = gdf_official_destinations_clipped.plot(ax=ax, color='r', lw=1, label='Official Data')
	_ = gdf_osm_destinations_clipped.plot(ax=ax, color='y', lw=1, label='OSM Data')

	ax.axis("off")
	if projected:
		# only make x/y equal-aspect if data are projected
		ax.set_aspect('equal')

	# create legend
	ax.legend()

	# save to disk
	fig.savefig(filepath, dpi=300, bbox_inches='tight', facecolor=fig.get_facecolor())
	print(ox.ts(), f'figure saved to disk at "{filepath}"')

	plt.close()
	return fig, ax

def plot_core_data(osm_core_dests, official_core_dests, gdf_osm_destinations_clipped, study_area, filepath, figsize=(10, 10), bgcolor='#333333', projected=True):
	"""
	Plot the OSM vs official destinations and save to disk.

	Parameters
	----------
	osm_core_dests : geopandas.GeoDataFrame
		the osm destinations
	official_core_dests : geopandas.GeoDataFrame
		the official destinations
	gdf_osm_destinations_clipped
	study_area : shapely.Polygon or shapely.MultiPolygon
		the study area boundary
	filepath : str
		path to save figure as file
	figsize : tuple
		size of plotting figure
	bgcolor : str
		background color of plot
	projected : bool
		True if gdfs are projected rather than lat-lng

	Returns
	-------
	fig, ax : tuple
	"""

	fig, ax = plt.subplots(figsize=figsize, facecolor=bgcolor)
	ax.set_facecolor(bgcolor)

	# turn study_area polygon into gdf with correct CRS
	gdf_boundary = gpd.GeoDataFrame(geometry=[study_area], crs=gdf_osm_destinations_clipped.crs)

	# plot study area, then official destinations, then osm destinations as layers
	_ = gdf_boundary.plot(ax=ax, facecolor='k', label='Study Area')
	_ = official_core_dests.plot(ax=ax, color='r', lw=1, label='Official Data')
	_ = osm_core_dests.plot(ax=ax, color='y', lw=1, label='OSM Data')

	ax.axis("off")
	if projected:
		# only make x/y equal-aspect if data are projected
		ax.set_aspect('equal')

	# create legend
	ax.legend()

	# save to disk
	fig.savefig(filepath, dpi=300, bbox_inches='tight', facecolor=fig.get_facecolor())
	print(ox.ts(), f'figure saved to disk at "{filepath}"')

	plt.close()
	return fig, ax

def calculate_intersect(a, b, dist):
	"""
	Calculate the count of destinations from the official and the OSM dataset that intersect with different buffer.

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
	a_buff_prop, b_buff_prop
		the proportion of buffered a destinations that intersect with a buffered b destinations,
		the proportion of buffered b destinations that intersect with a buffered a destinations
	"""

	# focus on the geography of each gdf
	a_geography = a['geometry']
	b_geography = b['geometry']

	# buffer each by the current distance
	a_buff = a_geography.buffer(dist)
	b_buff = b_geography.buffer(dist)

	# take the unary union of each's buffered geometry
	a_buff_unary = a_buff.unary_union
	b_buff_unary = b_buff.unary_union

	# create a list of the destinations that intersect between datasets
	a_buff_overlap = []
	for dest in a_buff:
		if dest.intersects(b_buff_unary):
			a_buff_overlap.append(dest)

	b_buff_overlap = []
	for dest in b_buff:
		if dest.intersects(a_buff_unary):
			b_buff_overlap.append(dest)

	# find the proportion of destinations that intersect between datasets out of total destination
	a_buff_prop = len(a_buff_overlap) / len(a_geography)
	b_buff_prop = len(b_buff_overlap) / len(a_geography)

	return a_buff_prop, b_buff_prop
