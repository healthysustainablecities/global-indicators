# folder = '../data'
folder = '../sample_data'
to_crs = {'init': 'epsg:32632'}
# graphmlName = '../data/odense_dk_2019_10000m_pedestrian_osm_20190902.graphml'
graphmlName = '../sample_graphml'

graphmlProj_name = 'odense_dk_2019_10000m_pedestrian_osm_20190902_proj.graphml'
# graphmlProj_name = 'sample_graphml_proj'

geopackagePath = '../sample_data/odense_dk_2019.gpkg'
# geopackagePath = '../sample_data/sample_odense.gpkg'
samplePointsData_withoutNan = "samplePointsData_withoutNan"
samplePoints = 'urban_sample_points'
destinations = 'destinations'
hex250 = 'pop_ghs_2015'
# public open space
pos = 'aos_nodes_30m_line'
nodes = 'nodes'
edges = 'edges'
# output_gpkgPath = '../data/global_indicators_city.gpkg'
output_hex_250m = '../sample_data/global_indicators_hex_250m.gpkg'
accessibility_distance = 500
supermarket = 'Supermarket'
convenience = 'Convenience'
PT = 'Public transport stop (any)'

# fieldNames for sample data
samplePoint_fieldNames = {
    'sp_local_nh_avg_pop_density': "sp_local_nh_avg_pop_density",
    'sp_local_nh_avg_intersection_density':
    'sp_local_nh_avg_intersection_density',
    'sp_nearest_node_supermarket_dist': 'sp_nearest_node_supermarket_dist',
    'sp_nearest_node_supermarket_binary': 'sp_nearest_node_supermarket_binary',
    'sp_nearest_node_convenience_dist': 'sp_nearest_node_convenience_dist',
    'sp_nearest_node_convenience_binary': 'sp_nearest_node_convenience_binary',
    'sp_nearest_node_pt_dist': 'sp_nearest_node_pt_dist',
    'sp_nearest_node_pt_binary': 'sp_nearest_node_pt_binary',
    'sp_nearest_node_pos_dist': 'sp_nearest_node_pos_dist',
    'sp_nearest_node_pos_binary': 'sp_nearest_node_pos_binary',
    'sp_daily_living_score': 'sp_daily_living_score',
    'sp_zscore_local_nh_avgpopdensity': 'sp_zscore_local_nh_avgpopdensity',
    'sp_zscore_local_nh_avgintdensity': 'sp_zscore_local_nh_avgintdensity',
    'sp_zscore_daily_living_score': 'sp_zscore_daily_living_score',
    'sp_walkability_index': 'sp_walkability_index'
}

# fieldNames for hex
hex_fieldNames = {
    'index': 'index',
    'study_region': 'study_region',
    'urban_sample_point_count': 'urban_sample_point_count',
    'pct_access_500m_supermarkets': 'pct_access_500m_supermarkets',
    'pct_access_500m_convenience': 'pct_access_500m_convenience',
    'pct_access_500m_pt_any': 'pct_access_500m_pt_any',
    'pct_access_500m_public_open_space': 'pct_access_500m_public_open_space',
    'local_nh_population_density': 'local_nh_population_density',
    'local_nh_intersection_density': 'local_nh_intersection_density',
    'local_daily_living': 'local_daily_living',
    'local_walkability': 'local_walkability',
    'all_cities_z_nh_population_density': 'all_cities_z_nh_population_density',
    'all_cities_z_nh_intersection_density':
    'all_cities_z_nh_intersection_density',
    'all_cities_z_daily_living': 'all_cities_z_daily_living',
    'all_cities_walkability': 'all_cities_walkability',
    'geometry': 'geometry'
}
