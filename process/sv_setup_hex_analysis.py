import pandas as pd
import geopandas as gpd
import sv_config as sc


def aggregation(gdf_hex, gdf_samplePoint, fieldNames):
    """
    calculate aggregation for hex
    
    Arguments:
        gdf_hex {geopandas} -- [hex]
        gdf_samplePoint {geopandas} -- [sample point]
        fieldNames {list(zip)} -- [fieldNames from sample point and hex ]
    """
    for names in fieldNames:
        df = gdf_samplePoint[['hex_id', names[0]]].groupby('hex_id').mean()
        gdf_hex = gdf_hex.join(df, how='left', on='index')
        gdf_hex.rename(columns={names[0]: names[1]}, inplace=True)
    return gdf_hex


def organiseColumnName(gdf, fieldNames):
    """organise the gdf column name to make it match the desired result
    note: at this stage, some of the fields haven't had number
    Arguments:
        gdf {geodataframe} -- [the hex should be rename the column]
        fieldNames {[list]} -- [all the desired field names]
    """
    fieldNamesOld = gdf.columns.to_list()
    fields = []
    for i in fieldNamesOld:
        if i in fieldNames:
            fields.append(i)
    return gdf[fields].copy()
