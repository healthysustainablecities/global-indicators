
import json
import os

import geopandas as gpd
import matplotlib.pyplot as plt

import osmnx as ox


def load_data(osm_graphml_path, osm_buffer_gpkg_path, official_streets_shp_path):
    """
    Load the street network edges and study boundary.

    Parameters
    ----------
    osm_graphml_path : str
    osm_buffer_gpkg_path : str
    official_streets_shp_path : str

    Returns
    -------
    gdf_osm_streets_clipped, gdf_official_streets_clipped, study_area : tuple
        (GeoDataFrame, GeoDataFrame, shapely.geometry.MultiPolygon)
    """

    # load the study area boundary as a shapely (multi)polygon
    gdf_study_area = gpd.read_file(osm_buffer_gpkg_path, layer='urban_study_region')
    study_area = gdf_study_area['geometry'].iloc[0]

    # load the official streets shapefile
    gdf_official_streets = gpd.read_file(official_streets_shp_path)

    # load the graph, make it undirected, then get edges GeoDataFrame
    G = ox.load_graphml(osm_graphml_path)
    G_undir = ox.get_undirected(G)
    gdf_osm_streets = ox.graph_to_gdfs(G_undir, nodes=False)

    # Project the data to a common crs
    gdf_osm_streets = gdf_osm_streets.to_crs(gdf_study_area.crs)
    assert gdf_osm_streets.crs == gdf_official_streets.crs == gdf_study_area.crs

    # spatially clip the streets to the study area boundary
    gdf_osm_streets_clipped, gdf_official_streets_clipped = _clip_data(gdf_osm_streets, gdf_official_streets, study_area)
    return gdf_osm_streets_clipped, gdf_official_streets_clipped, study_area


def _clip_data(gdf_osm_streets, gdf_official_streets, study_area):
    """
    Spatially clip datasets to study area boundary

    Parameters
    ----------
    gdf_osm_streets : geopandas.GeoDataFrame
    gdf_official_streets : geopandas.GeoDataFrame
    study_area : shapely.Polygon or shapely.MultiPolygon

    Returns
    -------
    gdf_osm_streets_clipped, gdf_official_streets_clipped : tuple
        (GeoDataFrame, GeoDataFrame)
    """

    # clip the official streets to the study area (multi)polygon
    mask = gdf_official_streets.intersects(study_area)
    gdf_official_streets_clipped = gdf_official_streets[mask]

    # clip the OSM streets to the study area (multi)polygon
    mask = gdf_osm_streets.intersects(study_area)
    gdf_osm_streets_clipped = gdf_osm_streets[mask]

    return gdf_osm_streets_clipped, gdf_official_streets_clipped


def plot_data(gdf_osm, gdf_official, study_area, figsize=(10, 10), bgcolor='#333333', projected=True):
    """
    Parameters
    ----------
    gdf_osm : geopandas.GeoDataFrame
    gdf_official : geopandas.GeoDataFrame
    study_area : shapely.Polygon or shapely.MultiPolygon
    figsize : tuple
    bgcolor : str
    projected : bool

    Returns
    -------
    fig, ax : tuple
    """

    fig, ax = plt.subplots(figsize=figsize, facecolor=bgcolor)
    ax.set_facecolor(bgcolor)

    # turn study_area polygon into gdf with correct CRS
    assert gdf_osm.crs == gdf_official.crs
    gdf_boundary = gpd.GeoDataFrame(geometry=[study_area], crs=gdf_osm.crs)

    # plot study area, then official streets, then osm streets as layers
    layer1 = gdf_boundary.plot(ax=ax, facecolor='k', label='Study Area')
    layer2 = gdf_official.plot(ax=ax, color='r', lw=1, label='Official Data')
    layer3 = gdf_osm.plot(ax=ax, color='y', lw=1, label='OSM Data')

    ax.axis("off")
    if projected:
        # only make x/y equal-aspect if data are projected
        ax.set_aspect('equal')

    ax.legend()
    return fig, ax


# Calculate the total length of network
# Dataname can be either 'gdf_osm' or 'gdf_official'
def total_length(dataname):
    totallength = 0
    count = 0
    length = dataname.length
    for i in length:
        count += 1
        totallength += i
    print(totallength + "; " + count)


# Calculate area intersection with various buffering
# Dataname can be either 'official_buffer' or 'osm_buffer'
def buffer_intersected(x, dataname):
    buff = x
    while buff < 20:
        official_buffer = official_data.buffer(buff)
        osm_buffer = osm_data.buffer(buff)
        total = 0
        area = dataname.area
        for i in area:
            total += i
        print(dataname + ": " + total)


# Calculate shared area of intersection with various buffering
def shared_area(x):
    buff = x
    percent_list = []
    percent_dict = {}
    while buff < 20:
        official_buffer = official_data.buffer(buff)
        osm_buffer = osm_data.buffer(buff)
        intersected = gpd.clip(official_buffer, osm_buffer)
        totalshare = 0
        in_areas = intersected.area
        for i in in_areas:
            totalshare += i
        print('Share of Buffered Area:' + totalshare)

        percent_official_intersected = totalshare*100/official_total

        print("intersected: ", totalshare)
        print("intersected length: ", len(intersected))
        print("percent_official_intersected: ", percent_official_intersected)

        percent_dict[buff] = percent_official_intersected
        percent_list.append((buff, percent_official_intersected))

        for item in percent_list:
            print("buffer: ", item[0])
            print("Percent area intersected: ", item[1])
            print("-----------------------")
