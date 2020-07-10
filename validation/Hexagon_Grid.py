import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.patches import RegularPolygon
import shapely
from shapely.geometry import Polygon
from matplotlib.patches import RegularPolygon

def hex_plot(geo_pkg_path):

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
        hcoord = np.arange(xmin,xmax,w) + (rows%2)*w/2
        vcoord = [ymax- rows*d*0.75]*n_cols
        for x, y in zip(hcoord, vcoord):#, colors):
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
    hex_grid = gpd.GeoDataFrame({'geometry': array_of_hexes})
    return hex_grid
