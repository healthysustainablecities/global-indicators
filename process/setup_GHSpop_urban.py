################################################################################
# Script:  setup_GHSpop_urban.py
# Purpose: Set up study region population and urban built up areas
# Author:  Shirley Liu
# Date:    201908
# Description: this script contains basic functions to set up population and study region built up area from GHSL raster files

################################################################################

import rasterio
from rasterio.mask import mask
from rasterio import features

import networkx as nx
import time 
import os
import osmnx as ox
import matplotlib.pyplot as plt
from matplotlib import pyplot
import numpy as np
import requests
import pandas as pd
import geopandas as gpd
import json

from shapely.geometry import shape, Point, LineString, Polygon
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.merge import merge
from rasterio.plot import show
from rasterio.features import shapes

from rasterio.merge import merge
from rasterio.plot import show
from config import *

ox.config(use_cache=True, log_console=True)


################################################################################


def save_studyregion_GHS_raster(raster_datasets, raster_filepath):
    """
    Combine and save GHS raster mosaic datasets to one raster image
    
    Parameters
    ----------
    raster_datasets : list
        list of raster datasets
    raster_filepath : string
        filepath to save the output raster image
    Returns
    -------
    None
    """
    # load GHS population raster
    
    #read and load datasets
    raster_pop_to_mosaic = []
    for dataset in raster_datasets:
        src = rasterio.open(dataset)
        raster_pop_to_mosaic.append(src)
    # merge raster dataset to get complete regional data
    raster_pop_mosaic, out_trans = merge(raster_pop_to_mosaic)
    
    out_meta = src.meta.copy()

    # Update the metadata
    crs = src.crs  #projection
    out_meta.update({"driver": "GTiff", 
                 "height": raster_pop_mosaic.shape[1], 
                 "width": raster_pop_mosaic.shape[2], 
                 "transform": out_trans, 
                 "crs": crs
                }
               )
    
    with rasterio.open(raster_filepath, "w", **out_meta) as dest:
        dest.write(raster_pop_mosaic)
        
    show(raster_pop_mosaic, cmap='terrain')
################################################################################



def clip_studyregion_GHS_raster(clipping_boundary, raster_filepath, raster_clipped_filepath):
    """
    Clip studyregion raster based on study region boundary 
    
    Parameters
    ----------
    clipping_boundary : geodataframe
        study region geodataframe
    raster_filepath : string
        filepath of input raster image
    raster_clipped_filepath : string 
         filepath to save output raster

    Returns
    -------
    output raster
 
    """
    with rasterio.open(raster_filepath) as full_raster:
        # set pop_vector to match crs of input raster
        # in theory, works if epsg is otherwise detectable in rasterio
        clipping_boundary.to_crs(full_raster.crs,inplace=True)
        coords = [json.loads(clipping_boundary.to_json())['features'][0]['geometry']]
        out_img, out_transform = mask(full_raster, coords, crop=True)
        out_meta = full_raster.meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": out_img.shape[1],
            "width":  out_img.shape[2],
            "transform": out_transform }) 
    with rasterio.open(raster_clipped_filepath, "w", **out_meta) as dest:
        dest.write(out_img) 
    
    raster = rasterio.open(raster_clipped_filepath)
    return raster
    show(raster, cmap='terrain')

################################################################################
def reproject_raster(inpath, outpath, new_crs):
    """
    Reproject/define projection of studyregion raster
    
    Parameters
    ----------
    inpath : string
        filepath of input raster image
    outpath : string 
        filepath to save output raster
    new_crs : dict
        new projected crs

    Returns
    -------
    output raster
 
    """
    # CRS for web meractor
    dst_crs = new_crs
    with rasterio.open(inpath) as src:
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds)
        kwargs = src.meta.copy()
        kwargs.update({
            'crs': dst_crs,
            'transform': transform,
            'width': width,
            'height': height
        })
        with rasterio.open(outpath, 'w', **kwargs) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=dst_crs,
                    resampling=Resampling.nearest)
        raster_proj = rasterio.open(outpath)
        return raster_proj


################################################################################



def raster_to_gdf(raster_filepath, to_crs):
    """
    Convert raster to geodataframe
    
    Parameters
    ----------
    raster_filepath : string
        filepath of input raster image
    to_crs : dict
        new projected crs

    Returns
    -------
    geodataframe
 
    """
    # extract shapes of pop raster features 
    #The result is a generator of GeoJSON features


    mask = None
    with rasterio.open(raster_filepath) as src:
        image = src.read(1) # first band
        results = (
        {'properties': {'raster_val': v}, 'geometry': s}
        for i, (s, v) 
        in enumerate(shapes(image, mask=mask, transform=src.transform)))
    
    # That you can transform into shapely geometries

    geoms = list(results)
    # Create geopandas Dataframe and enable easy to use functionalities of spatial join, plotting, ESRI shapefile etc.
    polygonized_raster_gdf = gpd.GeoDataFrame.from_features(geoms)
    polygonized_raster_gdf = polygonized_raster_gdf[(polygonized_raster_gdf.raster_val != -200) & (polygonized_raster_gdf.raster_val != 0)]

    polygonized_raster_gdf.crs = to_crs
    return polygonized_raster_gdf 
################################################################################

