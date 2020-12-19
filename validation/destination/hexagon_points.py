import json
import os

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import RegularPolygon
from shapely.geometry import Polygon

import osmnx as ox

# configure script
cities = ["olomouc", "sao_paulo"]
indicators_filepath = "./hex_indicators.csv"
figure_filepath = "./fig/hexbins-{city}.png"

if not os.path.exists("./fig/"):
    os.makedirs("./fig/")


def load_data(osm_buffer_gpkg_path, official_dests_filepath, destinations_column, destinations_values):

    # load the study area boundary as a shapely (multi)polygon
    gdf_study_area = gpd.read_file(osm_buffer_gpkg_path, layer="urban_study_region")
    study_area = gdf_study_area["geometry"].iloc[0]
    print(ox.ts(), "loaded study area boundary")

    # load the official destinations shapefile
    # retain only rows with desired values in the destinations column
    gdf_official_destinations = gpd.read_file(official_dests_filepath)
    mask = gdf_official_destinations[destinations_column].isin(destinations_values)
    gdf_official_destinations = gdf_official_destinations[mask]
    print(ox.ts(), "loaded and filtered official destinations shapefile")

    # load the osm destinations shapefile
    gdf_osm = gpd.read_file(osm_buffer_gpkg_path, layer="destinations")
    gdf_osm_destinations = gdf_osm[gdf_osm["dest_name"] == "fresh_food_market"]
    print(ox.ts(), "loaded osm destinations shapefile")

    # project the data to a common crs
    crs = gdf_study_area.crs
    if gdf_official_destinations.crs != crs:
        gdf_official_destinations = gdf_official_destinations.to_crs(crs)
        print(ox.ts(), "projected official destinations")
    if gdf_osm_destinations.crs != crs:
        gdf_osm_destinations = gdf_osm_destinations.to_crs(crs)
        print(ox.ts(), "projected osm destinations")

    # spatially clip the destinationss to the study area boundary
    import warnings

    warnings.filterwarnings("ignore", "GeoSeries.notna", UserWarning)  # temp warning suppression
    gdf_osm_destinations_clipped = gpd.clip(gdf_osm_destinations, study_area)
    gdf_official_destinations_clipped = gpd.clip(gdf_official_destinations, study_area)
    print(ox.ts(), "clipped osm/official destinations to study area boundary")

    # double-check everything has same CRS, then return
    assert gdf_study_area.crs == gdf_osm_destinations_clipped.crs == gdf_official_destinations_clipped.crs
    return study_area, gdf_osm_destinations_clipped, gdf_official_destinations_clipped


def hex_bins(osm_buffer_gpkg_path, study_area, gdf_osm_destinations_clipped):

    boundary = gpd.read_file(osm_buffer_gpkg_path, layer="urban_study_region")
    gdf_boundary = boundary["geometry"]

    xmin, ymin, xmax, ymax = gdf_boundary.total_bounds  # lat-long of 2 corners
    xmin -= 500
    xmax += 500
    ymin -= 500
    ymax += 500
    # East-West extent of urban_study_region
    EW = xmax - xmin
    # North-South extent of urban_study_region
    NS = ymax - ymin
    # Hexagon bins diameter should equal 500 meters
    d = 500
    # horizontal width of hexagon = w = d* sin(60)
    w = d * np.sin(np.pi / 3)
    # Approximate number of hexagons per row = EW/w
    n_cols = int(EW / d) + 1
    # Approximate number of hexagons per column = NS/d
    n_rows = int(NS / w) + 1

    w = (xmax - xmin) / n_cols  # width of hexagon
    d = w / np.sin(np.pi / 3)  # diameter of hexagon 500 meters
    array_of_hexes = []

    # +1 added to n_rows since the range function runs from 0 through (n-1), and the number of rows of hexgons plotted
    # was one less than the expcted number of rows.
    for rows in range(0, n_rows + 1):
        hcoord = np.arange(xmin, xmax, w) + (rows % 2) * w / 2
        vcoord = [ymax - rows * d * 0.75] * n_cols
        for x, y in zip(hcoord, vcoord):
            hexes = RegularPolygon((x, y), numVertices=6, radius=d / 2, alpha=0.2, edgecolor="k")
            verts = hexes.get_path().vertices
            trans = hexes.get_patch_transform()
            points = trans.transform(verts)
            array_of_hexes.append(Polygon(points))

    # turn study_area polygon into gdf with correct CRS
    gdf_boundary = gpd.GeoDataFrame(geometry=[study_area], crs=gdf_osm_destinations_clipped.crs)
    gdf_boundary = gpd.GeoDataFrame(gdf_boundary)

    hex_grid = gpd.GeoDataFrame({"geometry": array_of_hexes})
    hex_grid_clipped = gpd.overlay(hex_grid, gdf_boundary)
    hex_grid_clipped = gpd.GeoDataFrame(hex_grid_clipped, geometry="geometry")

    return gdf_boundary, hex_grid_clipped


def plot_hex_bins(
    gdf_boundary,
    hex_grid_clipped,
    gdf_official_destinations_clipped,
    gdf_osm_destinations_clipped,
    filepath,
    figsize=(10, 10),
    bgcolor="#333333",
    projected=True,
):

    fig, ax = plt.subplots(figsize=figsize, facecolor=bgcolor)
    ax.set_facecolor(bgcolor)

    # plot study area, then official destinations, then osm destinations as layers
    _ = gdf_boundary.plot(ax=ax, facecolor="k", label="Study Area")
    _ = hex_grid_clipped.plot(ax=ax, facecolor="k", edgecolor="w", lw=2, label="Hex Bins")
    _ = gdf_official_destinations_clipped.plot(ax=ax, color="r", lw=1, label="Official Data")
    _ = gdf_osm_destinations_clipped.plot(ax=ax, color="y", lw=1, label="OSM Data")

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


def calc_hex_indicators(hex_grid_clipped, gdf_osm_destinations, gdf_official_destinations):
    osm_true = []
    official_true = []
    osm_percentages = []
    official_percentages = []
    weight_count = 0
    osm_layer_df = gpd.GeoDataFrame(gdf_osm_destinations)
    official_layer_df = gpd.GeoDataFrame(gdf_official_destinations)
    # Loop through hexagon bins
    for _, hexagon in enumerate(hex_grid_clipped["geometry"]):
        osm_count = 0
        official_count = 0
        total_count = 0
        # Loop through OSM Points
        for row in osm_layer_df.iterrows():
            layer_point = row[1]["geometry"]
            if hexagon.contains(layer_point):
                osm_count += 1
                total_count += 1
        # Loop through Official Points
        for row in official_layer_df.iterrows():
            layer_point = row[1]["geometry"]
            if hexagon.contains(layer_point):
                official_count += 1
                total_count += 1

        percentage_osm = osm_count / total_count if total_count else 0
        percentage_official = official_count / total_count if total_count else 0
        # weight = True if bool(osm_count) == bool(official_count) else False
        if bool(osm_count) == bool(official_count):
            weight_count += 1
            osm_true.append(osm_count)
            official_true.append(official_count)
        osm_percentages.append(percentage_osm)
        official_percentages.append(percentage_official)

    weight_percentage = weight_count / len(hex_grid_clipped["geometry"])
    osm_mean = sum(osm_percentages) / len(hex_grid_clipped["geometry"])
    # osm_median = statistics.median(osm_percentages)
    osm_true_mean = sum(osm_true) / weight_count
    # osm_true_median = statistics.median(osm_true)
    official_mean = sum(official_percentages) / len(hex_grid_clipped["geometry"])
    # official_median = statistics.median(official_percentages)
    official_true_mean = sum(official_true) / weight_count
    # official_true_median = statistics.median(official_true)

    return weight_percentage, osm_mean, official_mean, osm_true_mean, official_true_mean


# RUN THE SCRIPT
indicators = {}
for city in cities:

    print(ox.ts(), f"begin processing {city}")
    indicators[city] = {}

    # load this city's configs
    with open(f"../configuration/{city}.json") as f:
        config = json.load(f)

    # load destination gdfs from osm graph and official shapefile
    study_area, gdf_osm_destinations_clipped, gdf_official_destinations_clipped = load_data(
        config["osm_buffer_gpkg_path"],
        config["official_dests_filepath"],
        config["destinations_column"],
        config["destinations_values"],
    )

    # create plot of hexbins for the city
    gdf_boundary, hex_grid_clipped = hex_bins(config["osm_buffer_gpkg_path"], study_area, gdf_osm_destinations_clipped)

    # plot map of study area, hex bins, and osm and official destinations, save to disk
    fp = figure_filepath.format(city=city)
    fig, ax = plot_hex_bins(
        gdf_boundary, hex_grid_clipped, gdf_official_destinations_clipped, gdf_osm_destinations_clipped, fp
    )

    # calculate the indicators at the hexbin level
    weight_percentage, osm_mean, official_mean, osm_true_mean, official_true_mean = calc_hex_indicators(
        hex_grid_clipped, gdf_osm_destinations_clipped, gdf_official_destinations_clipped
    )
    indicators[city]["weight_percentage"] = weight_percentage
    indicators[city]["osm_mean"] = osm_mean
    indicators[city]["official_mean"] = official_mean
    indicators[city]["osm_true_mean"] = osm_true_mean
    indicators[city]["official_true_meann"] = official_true_mean
    print(ox.ts(), "created indictors at hexbin level")

# turn indicators into a dataframe and save to disk
df_ind = pd.DataFrame(indicators).T
df_ind.to_csv(indicators_filepath, index=True, encoding="utf-8")
print(ox.ts(), f'all done, saved indicators to disk at "{indicators_filepath}"')
