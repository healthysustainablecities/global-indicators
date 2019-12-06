"""
now it works on all cities together, calculate all_cities_zscore for each study region
"""

import geopandas as gpd
import pandas as pd
import os
import time
import sv_config as sc
import sv_setup_hexes_allCities as ssh

startTime = time.time()
dirname = os.path.dirname(__file__)
gpkg_input = os.path.join(dirname, sc.output_cities)
gdf_layers = []
layers = []
for i in list(sc.layerNames.values()):
    try:
        gdf = gpd.read_file(gpkg_input, layer=i)
        gdf = gdf.reindex(columns=sorted(gdf.columns))
        gdf_layers.append(gdf)
        layers.append(i)
    except ValueError as e:
        print(e)

# create a big dataframe(all_cities_hex_df) according to gdf_layers
all_cities_hex_df = pd.concat(gdf_layers, ignore_index=True)

fieldNames = [
    sc.city_fieldNames['pop_nh_pop_density'],
    sc.city_fieldNames['pop_nh_intersection_density'],
    sc.city_fieldNames['pop_daily_living']
]

fieldNames_new = [
    sc.city_fieldNames['all_cities_pop_z_nh_population_density'],
    sc.city_fieldNames['all_cities_pop_z_nh_intersection_density'],
    sc.city_fieldNames['all_cities_pop_z_daily_living']
]

fieldNames_zip = list(zip(fieldNames, fieldNames_new))

for index, layer in enumerate(gdf_layers):
    for field_zip in fieldNames_zip:
        mean, std = ssh.getMeanStd(all_cities_hex_df, field_zip[0])
        layer[field_zip[1]] = (layer[field_zip[0]] - mean) / std
    # sum all three new fields
    layer[sc.hex_fieldNames['all_cities_walkability']] = layer[
        fieldNames_new].sum(axis=1)
    layer = layer.reindex(columns=sorted(layer.columns))
    layer.to_file(gpkg_input, layer=layers[index], driver='GPKG')
