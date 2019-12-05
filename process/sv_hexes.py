"""
calculate aggregation for hexes
"""

import geopandas as gpd
import pandas as pd
import osmnx as ox
import numpy as np
import sv_config as sc
import sv_setup_hex_analysis as ssh
import os
import time

startTime = time.time()
dirname = os.path.dirname(__file__)
# input geopackage, read processed sample point and hex
gpkg_input = os.path.join(dirname, sc.geopackagePath)
gdf_samplepoint = gpd.read_file(gpkg_input,
                                layer=sc.samplePointsData_withoutNan)
gdf_hex = gpd.read_file(gpkg_input, layer=sc.hex250)
# output geopackage
gpkg_output = os.path.join(dirname, sc.output_hex_250m)

# calculate all the "urban_sample_point_count" for each hex
samplepoint_count = gdf_samplepoint['hex_id'].value_counts()
gdf_hex_new = gdf_hex.join(samplepoint_count, how='inner', on='index')
gdf_hex_new.rename(columns={'hex_id': 'urban_sample_point_count'},
                   inplace=True)

# calculate aggregation for hex
fieldNames_from_samplePoint = [
    'sp_nearest_node_Supermarket_binary', 'sp_nearest_node_Convenience_binary',
    'sp_nearest_node_Public transport stop (any)_binary',
    'sp_nearest_node_aos_nodes_30m_line_binary', 'sp_local_nh_avg_pop_density',
    'sp_local_nh_avg_intersection_density', 'sp_daily_living_score',
    'sp_walkability_index'
]

fieldNames2hex = [
    'pct_access_500m_supermarkets', 'pct_access_500m_convenience',
    'pct_access_500m_pt_any', 'pct_access_500m_public_open_space',
    'local_nh_population_density', 'local_nh_intersection_density',
    'local_daily_living', 'local_walkability'
]

gdf_hex_new = ssh.aggregation(
    gdf_hex_new, gdf_samplepoint,
    list(zip(fieldNames_from_samplePoint, fieldNames2hex)))

# change accessibility to Percentage
fields = [
    'pct_access_500m_supermarkets', 'pct_access_500m_convenience',
    'pct_access_500m_pt_any', 'pct_access_500m_public_open_space'
]
gdf_hex_new[fields] = gdf_hex_new[fields] * 100

gdf_hex_new = ssh.organiseColumnName(gdf_hex_new,
                                     list(sc.hex_fieldNames.values()))

# save the gdf_hex_new to geopackage
gdf_hex_new.to_file(gpkg_output, layer='hex_temp', driver='GPKG')

print('Time is: {}'.format(time.time() - startTime))
print('finished.')
