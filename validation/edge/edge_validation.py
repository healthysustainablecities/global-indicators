import json
import os

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd

import osmnx as ox

# configure script
cities = ["olomouc", "belfast", "hong_kong"]
edge_buffer_dists = [10, 50]
indicators_filepath = "./indicators.csv"
figure_filepath = "./fig/street-comparison-{city}.png"

if not os.path.exists("./fig/"):
    os.makedirs("./fig/")


def load_data(osm_graphml_path, osm_buffer_gpkg_path, official_streets_gpkg_path):
    """
    Load the street network edges and study boundary.

    Parameters
    ----------
    osm_graphml_path : str
        path to the OSM graphml file
    osm_buffer_gpkg_path : str
        path to the buffered study area geopackage
    official_streets_gpkg_path : str
        path to the official streets shapefile

    Returns
    -------
    gdf_osm_streets_clipped, gdf_official_streets_clipped, study_area : tuple
        the osm streets (clipped to the study area), the official streets
        (clipped to the study area), and the study area polygon
    """

    # load the study area boundary as a shapely (multi)polygon
    gdf_study_area = gpd.read_file(osm_buffer_gpkg_path, layer="urban_study_region")
    study_area = gdf_study_area["geometry"].iloc[0]
    print(ox.ts(), "loaded study area boundary")

    # load the official streets shapefile
    gdf_official_streets = gpd.read_file(official_streets_gpkg_path)
    print(ox.ts(), "loaded official streets shapefile")

    # load the graph, make it undirected, then get edges GeoDataFrame
    gdf_osm_streets = ox.graph_to_gdfs(ox.get_undirected(ox.load_graphml(osm_graphml_path)), nodes=False)
    print(ox.ts(), "loaded osm edges and made undirected streets")

    # Project the data to a common crs
    crs = gdf_study_area.crs
    if gdf_osm_streets.crs != crs:
        gdf_osm_streets = gdf_osm_streets.to_crs(crs)
        print(ox.ts(), "projected osm streets")
    if gdf_official_streets.crs != crs:
        gdf_official_streets = gdf_official_streets.to_crs(crs)
        print(ox.ts(), "projected official streets")

    # spatially clip the streets to the study area boundary
    import warnings

    warnings.filterwarnings("ignore", "GeoSeries.notna", UserWarning)  # temp warning suppression
    gdf_osm_streets_clipped = gpd.clip(gdf_osm_streets, study_area)
    gdf_official_streets_clipped = gpd.clip(gdf_official_streets, study_area)
    print(ox.ts(), "clipped osm/official streets to study area boundary")

    # double-check everything has same CRS, then return
    assert gdf_osm_streets_clipped.crs == gdf_official_streets_clipped.crs == gdf_study_area.crs
    return gdf_osm_streets_clipped, gdf_official_streets_clipped, study_area


def plot_data(gdf_osm, gdf_official, study_area, filepath, figsize=(10, 10), bgcolor="#333333", projected=True):
    """
    Plot the OSM vs official streets and save to disk.

    Parameters
    ----------
    gdf_osm : geopandas.GeoDataFrame
        the osm streets
    gdf_official : geopandas.GeoDataFrame
        the official streets
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
    gdf_boundary = gpd.GeoDataFrame(geometry=[study_area], crs=gdf_osm.crs)

    # plot study area, then official streets, then osm streets as layers
    _ = gdf_boundary.plot(ax=ax, facecolor="k", label="Study Area")
    _ = gdf_official.plot(ax=ax, color="r", lw=1, label="Official Data")
    _ = gdf_osm.plot(ax=ax, color="y", lw=1, label="OSM Data")

    ax.axis("off")
    if projected:
        # only make x/y equal-aspect if data are projected
        ax.set_aspect("equal")

    # create legend
    ax.legend()

    # save to disk
    fig.savefig(filepath, dpi=300, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(ox.ts(), f'figure saved to disk at "{filepath}"')

    plt.close()
    return fig, ax


def total_edge_length_count(gdf_streets):
    """
    Calculate the total length and count of streets in gdf.

    Parameters
    ----------
    gdf_streets : geopandas.GeoDataFrame
        the osm or official streets

    Returns
    -------
    streets_total_length, streets_count : tuple
    """
    streets_total_length = gdf_streets.length.sum()
    streets_count = len(gdf_streets)
    return streets_total_length, streets_count


def calculate_overlap(a, b, dist):
    """
    Calculate the % overlap of a and b's lines and buffered lines' areas
    given different buffering distances.

    Parameters
    ----------
    a : geopandas.GeoDataFrame
        the osm streets
    b : geopandas.GeoDataFrame
        the osm streets
    dist : int
        buffer distance in meters

    Returns
    -------
    a_area_pct, b_area_pct, a_length_pct, b_length_pct : tuple
    """

    # buffer each by the current distance
    a_buff = a.buffer(dist)
    b_buff = b.buffer(dist)

    # take the unary union of each's buffered geometry
    a_buff_unary = a_buff.unary_union
    b_buff_unary = b_buff.unary_union

    # find the portion of each's buffered geometry that intersects with the other's buffered geometry
    a_buff_overlap = a_buff_unary.intersection(b_buff_unary)
    b_buff_overlap = b_buff_unary.intersection(a_buff_unary)

    # what % of each's buffered area does that intersecting portion comprise?
    a_area_pct = a_buff_overlap.area / a_buff_unary.area
    b_area_pct = b_buff_overlap.area / b_buff_unary.area

    # take the unary union of each's original unbuffered lines
    a_unary = a.unary_union
    b_unary = b.unary_union

    # find each's lines that intersect the intersecting buffered portion
    a_overlap = a_unary.intersection(a_buff_overlap)
    b_overlap = b_unary.intersection(b_buff_overlap)

    # what % of each's lines length does that intersecting portion comprise?
    a_length_pct = a_overlap.length / a_unary.length
    b_length_pct = b_overlap.length / b_unary.length

    return a_area_pct, b_area_pct, a_length_pct, b_length_pct


# RUN THE SCRIPT
indicators = {}
for city in cities:

    print(ox.ts(), f"begin processing {city}")
    indicators[city] = {}

    # load this city's configs
    with open(f"../configuration/{city}.json") as f:
        config = json.load(f)

    # load street gdfs from osm graph and official shapefile, then clip to study area boundary polygon
    gdf_osm_streets, gdf_official_streets, study_area = load_data(
        config["osm_graphml_path"], config["osm_buffer_gpkg_path"], config["official_streets_gpkg_path"]
    )

    # plot map of study area + osm and official streets, save to disk
    fp = figure_filepath.format(city=city)
    fig, ax = plot_data(gdf_osm_streets, gdf_official_streets, study_area, fp)

    # calculate total street length and edge count in each dataset, then add to indicators
    osm_total_length, osm_edge_count = total_edge_length_count(gdf_osm_streets)
    official_total_length, official_edge_count = total_edge_length_count(gdf_official_streets)
    indicators[city]["osm_total_length"] = osm_total_length
    indicators[city]["osm_edge_count"] = osm_edge_count
    indicators[city]["official_total_length"] = official_total_length
    indicators[city]["official_edge_count"] = official_edge_count
    print(ox.ts(), "calculated edge lengths and counts")

    # calculate the % overlaps of areas and lengths between osm and official streets with different buffer distances
    for dist in edge_buffer_dists:
        osm_area_pct, official_area_pct, osm_length_pct, official_length_pct = calculate_overlap(
            gdf_osm_streets, gdf_official_streets, dist
        )
        indicators[city][f"osm_area_pct_{dist}"] = osm_area_pct
        indicators[city][f"official_area_pct_{dist}"] = official_area_pct
        indicators[city][f"osm_length_pct_{dist}"] = osm_length_pct
        indicators[city][f"official_length_pct_{dist}"] = official_length_pct
        print(ox.ts(), f"calculated area/length of overlaps for buffer {dist}")

# turn indicators into a dataframe and save to disk
df_ind = pd.DataFrame(indicators).T
df_ind.to_csv(indicators_filepath, index=True, encoding="utf-8")
print(ox.ts(), f'all done, saved indicators to disk at "{indicators_filepath}"')
