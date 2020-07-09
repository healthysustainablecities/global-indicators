import json

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd

import osmnx as ox

# configure script
cities = ['olomouc', 'sao_paulo']
edge_buffer_dists = [10, 50]
indicators_filepath = './indicators.csv'
figure_filepath = './fig/destination-comparison-{city}.png'

def load_data(osm_buffer_gpkg_path, official_dests_filepath):
    """
    Load the city destinations and study boundary.

    Parameters
    ----------
    osm_buffer_gpkg_path : str
        path to the buffered study area geopackage
    official_dests_filepath : str
        path to the official destinations shapefile

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
    gdf_osm_destinations = gdf_osm[gdf_osm['dest_name'] == 'fresh_food_market']
    print(ox.ts(), 'loaded osm destinations shapefile')

	# Project the data to a common crs
    crs = gdf_study_area.crs
    if gdf_official_destinations.crs != crs:
        gdf_official_destinations = gdf_official_destinations.to_crs(crs)
        print(ox.ts(), 'projected official destinations')
    if gdf_osm_destinations.crs != crs:
        gdf_osm_destinations = gdf_osm_destinations.to_crs(crs)
        print(ox.ts(), 'projected osm destinations')
    
    # spatially clip the streets to the study area boundary
    import warnings; warnings.filterwarnings('ignore', 'GeoSeries.notna', UserWarning)  # temp warning suppression
    gdf_osm_destinations_clipped = gpd.clip(gdf_osm_destinations, study_area)
    gdf_official_destinations_clipped = gpd.clip(gdf_official_destinations, study_area)
    print(ox.ts(), 'clipped osm/official streets to study area boundary')


    # double-check everything has same CRS, then return
    assert gdf_study_area.crs == gdf_osm_destinations_clipped.crs == gdf_official_destinations_clipped.crs
    return study_area, gdf_osm_destinations_clipped, gdf_official_destinations_clipped

def plot_data(gdf_osm, gdf_official, study_area, filepath, figsize=(10, 10), bgcolor='#333333', projected=True):
    """
    Plot the OSM vs official streets and save to disk.

    Parameters
    ----------
    gdf_osm : geopandas.GeoDataFrame
        the osm destinations
    gdf_official : geopandas.GeoDataFrame
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

    # plot study area, then official streets, then osm streets as layers
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
    a_buff_overlap_count, b_buff_overlap_count
    	the count of intersections between the two gdf's, 
    	calculate the percentage of destinations that intersect, 
    	count of desitinations that overlap with gdf a
    	count of destiinations that overlap with gdf b
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

    # find the portion of each's buffered geometry that intersects with the other's buffered geometry
    a_buff_overlap_count = a_buff_unary.intersection(b_buff_unary)
    b_buff_overlap_count = b_buff_unary.intersection(a_buff_unary)

    return a_buff_overlap_count, b_buff_overlap_count

# def min_distance(a, b):
    """
    For every destination in dataframe a, find the distance to the closest dataset in dataframe b.

    Parameters
    ----------
    a : geopandas.GeoDataFrame
        the osm or offical destinations
    b : geopandas.GeoDataFrame
        the osm or offical destinations

    Returns
    -------
    nearest_distances; 
        list of the nearest distances for every destination in dataframe a
    """

#    nearest_distances = []
#    for destination in a:
#        nearest_distance = b.distance(destination).min()
#        nearest_distances.append(nearest_distance)
#    nearest_distances = a['nearest_distance']

# RUN THE SCRIPT
indicators = {}
for city in cities:

    print(ox.ts(), f'begin processing {city}')
    indicators[city] = {}

    # load this city's configs
    with open(f'../configuration/{city}.json') as f:
        config = json.load(f)

    # load destination gdfs from osm graph and official shapefile
    study_area, gdf_osm_destinations_clipped, gdf_official_destinations_clipped = load_data(config['osm_buffer_gpkg_path'],
                                                                                            config['official_dests_filepath'])
    # plot map of study area + osm and official streets, save to disk
    fp = figure_filepath.format(city=city)
    fig, ax = plot_data(gdf_osm_destinations_clipped, gdf_official_destinations_clipped, study_area, fp)

    # calculate total destination count in each dataset, then add to indicators
    osm_dest_count = len(gdf_osm_destinations_clipped)
    official_dest_count = len(gdf_official_destinations_clipped)
    indicators[city]['osm_dest_count'] = osm_dest_count
    indicators[city]['official_dest_count'] = official_dest_count
    print(ox.ts(), 'calculated destination counts')

    # calculate the % overlaps of areas and lengths between osm and official streets with different buffer distances
    for dist in edge_buffer_dists:
        osm_buff_overlap_count, official_buff_overlap_count = calculate_intersect(gdf_osm_destinations_clipped, gdf_official_destinations_clipped, dist)
        indicators[city][f'osm_buff_overlap_count_{dist}'] = osm_buff_overlap_count
        indicators[city][f'official_buff_overlap_count_{dist}'] = official_buff_overlap_count
    print(ox.ts(), f'calculated destination overlaps for buffer {dist}')

    # calculate the minimum distance from a destination in one dataset to the next
#    distfrom_osm_to_official = min_distance(gdf_osm_destinations, gdf_official_destinations)
#    distfrom_official_to_osm = min_distance(gdf_official_destinations, gdf_osm_destinations)
#    indicators[city]['distfrom_osm_to_official'] = distfrom_osm_to_official
#    indicators[city]['distfrom_official_to_osm'] = distfrom_official_to_osm

# turn indicators into a dataframe and save to disk
df_ind = pd.DataFrame(indicators).T
df_ind.to_csv(indicators_filepath, index=True, encoding='utf-8')
print(ox.ts(), f'all done, saved indicators to disk at "{indicators_filepath}"')

