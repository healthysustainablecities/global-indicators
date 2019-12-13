import json
import os
import time
import geopandas as gpd
import sv_config as sc
import sv_setup_hex_analysis as ssh


def cal_hexes(gpkg_input, gpkg_output, layer_samplepoint, layer_hex):
    """
    calculate aggregation for hexes
    gpkg_input: geopackage
    input geopackage full path
    gpkg_output: geopackage
    output geopackage: "global_indicators_hex_250m.gpkg"
    layer_samplepoint:
    sample point result, "samplePointsData"
    layer_hex:
    hex layer
    """
    # input geopackage, read processed sample point and hex
    gdf_samplepoint = gpd.read_file(gpkg_input, layer=layer_samplepoint)
    gdf_hex = gpd.read_file(gpkg_input, layer=layer_hex)
    # output geopackage
    gpkg_output = os.path.join(dirname, sc.output_hex_250m)

    # calculate all the "urban_sample_point_count" for each hex
    samplepoint_count = gdf_samplepoint['hex_id'].value_counts()
    gdf_hex_new = gdf_hex.join(samplepoint_count, how='inner', on='index')
    gdf_hex_new.rename(columns={'hex_id': 'urban_sample_point_count'},
                       inplace=True)

    # calculate aggregation for hex
    fieldNames_from_samplePoint = [
        'sp_nearest_node_Supermarket_binary',
        'sp_nearest_node_Convenience_binary',
        'sp_nearest_node_Public transport stop (any)_binary',
        'sp_nearest_node_aos_nodes_30m_line_binary',
        'sp_local_nh_avg_pop_density', 'sp_local_nh_avg_intersection_density',
        'sp_daily_living_score', 'sp_walkability_index'
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
    gdf_hex_new.to_file(gpkg_output, layer='odense', driver='GPKG')

    print('Time is: {}'.format(time.time() - startTime))
    print('finished.')


startTime = time.time()
dirname = os.path.dirname(__file__)
jsonFile = "./configuration/cities.json"
jsonPath = os.path.join(dirname, jsonFile)
with open(jsonPath) as json_file:
    config = json.load(json_file)
folder = config['folder']
gpkgNames = []
gpkgPath = []
for gpkg in config['gpkgnames'].values:
    gpkgNames.append(gpkg)
    gpkgPath.append(os.path.join(dirname, folder, gpkg))
