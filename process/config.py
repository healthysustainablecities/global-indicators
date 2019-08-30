# Script:  config.py
# Raw data configuration file
# Version: 201908
# Author:  Shirley Liu
# Description: All scripts within the data process folder draw on the parameters specified in this configeration file to source and output resources. 

places = {'phoenix' : 'Phoenix, Arizona, USA'} # all study regions name

placename = 'phoenix' # placename

region = 'Arizona, USA' # study region name

suffix = '_201905' # output data time

buffer_dist = 1e4 # study region buffer 10km

point_dist = 30 # sample point interval distance

network_type = 'walk' # OSM network type

distance = 1600 # accessibility distance
buffer_local = 50 # sausage buffer distance

# configure points-of-interests(pois) for daily living scores
shop = ['supermarket', 'convenience']

# projection parameters
crs = {'init': 'epsg:3742'} # study region starting crs
to_crs = {'init': 'epsg:4326'} # project from crs to lat-long

# data folder and file path
data_folder = '../data/Maricopa_County' # admintrative data folder
OSM_folder = '../data/OSM' # OSM resource folder
gtfs_folder = '../data/Transport' # transport gtfs data folder
pop_folder = '../data/Population' #population data from GHS

shape_filename = 'MC_Boundary.shp' # study region boundary file name
admin_filename = 'BlockGroup_Data.shp' # study region administrative data file
boundary_filepath = data_folder + '/' + shape_filename
admindata_filepath = data_folder + '/' + admin_filename

# OSM street network graph (projected and unprojected)
G_filename = '{studyregion}_{network_type}{suffix}.graphml'.format(studyregion = placename, network_type=network_type, suffix = suffix) # study region OSM network graphml filename
G_proj_filename = '{studyregion}_proj_{network_type}{suffix}.graphml'.format(studyregion = placename, network_type=network_type, suffix = suffix) # study region projected (UTM) OSM network graphml filename

G_filepath = OSM_folder + "/" + G_filename
G_proj_filepath = OSM_folder + "/" + G_proj_filename

# OSM street network shapefile (projected)
OSM_shapefile_name = '{studyregion}_proj_{network_type}{suffix}/{studyregion}_proj_{network_type}{suffix}.shp'.format(
        studyregion = placename, network_type=network_type, suffix = suffix) # study region OSM network shapefile name
OSM_shapefile_path = OSM_folder + '/' + OSM_shapefile_name  # study region OSM network shapefile path

# OSM street network within urban bulitup areas shapefile (projected)
urban_OSM_filename = '{studyregion}_proj_urban_walk{suffix}/{studyregion}_proj_urban_walk{suffix}.shp'.format(
        studyregion = placename, suffix = suffix)
urban_OSM_filepath = OSM_folder + "/" + urban_OSM_filename

# study region urban built-up area shapefile
builtup_filename = 'GHS_proj_2014builtup_250m_{studyregion}/GHS_proj_2014builtup_250m_{studyregion}.shp'.format(
        studyregion = placename)
builtup_filepath = OSM_folder + "/" + builtup_filename

# study region urban area sample point shapefile
samplepoint_shapefilename = '{studyregion}_urban_sample_points{suffix}/{studyregion}_urban_sample_points{suffix}.shp'.format(
        studyregion = placename, network_type=network_type, suffix = suffix) # study region (urban) sample points
samplepoint_filepath = OSM_folder + '/' + samplepoint_shapefilename

# sample point with stats variable shapefile 
samplepoint_stats_shapefilename = '{studyregion}_urban_sample_points_stats{suffix}/{studyregion}_urban_sample_points_stats{suffix}.shp'.format(
        studyregion = placename, network_type=network_type, suffix = suffix) # study region (urban) sample points stats
samplepoint_stats_shapefile_path = OSM_folder + '/' + samplepoint_stats_shapefilename

#cofigure point of interest of daily living filename and file path
poi_filename = '{}_pois_{}.csv'.format(placename, '_'.join(shop))
poi_filepath = OSM_folder + "/" + poi_filename

#frequent bus stop file path
frequent_stop_filename = 'gtfs_phx/stop_30_mins_bus_final.csv'
frequent_stop_filepath = gtfs_folder + "/" + frequent_stop_filename

# in order to get complete Phoenix area population, we need to get four parts of GHS raster files
population_raster_file1 = '../data/Population/GHS_POP_E2015_GLOBE_R2019A_54009_250_V1_0_7_4/GHS_POP_E2015_GLOBE_R2019A_54009_250_V1_0_7_4.tif'
population_raster_file2 = '../data/Population/GHS_POP_E2015_GLOBE_R2019A_54009_250_V1_0_7_5/GHS_POP_E2015_GLOBE_R2019A_54009_250_V1_0_7_5.tif'
population_raster_file3 = '../data/Population/GHS_POP_E2015_GLOBE_R2019A_54009_250_V1_0_8_4/GHS_POP_E2015_GLOBE_R2019A_54009_250_V1_0_8_4.tif'
population_raster_file4 = '../data/Population/GHS_POP_E2015_GLOBE_R2019A_54009_250_V1_0_8_5/GHS_POP_E2015_GLOBE_R2019A_54009_250_V1_0_8_5.tif'

# in order to get complete Phoenix area Built-up, we need to get four parts of GHS raster files
urban_raster_file1 = '../data/Population/GHS_BUILT_LDS2014_GLOBE_R2018A_54009_250_V2_0_7_4/GHS_BUILT_LDS2014_GLOBE_R2018A_54009_250_V2_0_7_4.tif'
urban_raster_file2 = '../data/Population/GHS_BUILT_LDS2014_GLOBE_R2018A_54009_250_V2_0_7_5/GHS_BUILT_LDS2014_GLOBE_R2018A_54009_250_V2_0_7_5.tif'
urban_raster_file3 = '../data/Population/GHS_BUILT_LDS2014_GLOBE_R2018A_54009_250_V2_0_8_4/GHS_BUILT_LDS2014_GLOBE_R2018A_54009_250_V2_0_8_4.tif'
urban_raster_file4 = '../data/Population/GHS_BUILT_LDS2014_GLOBE_R2018A_54009_250_V2_0_8_5/GHS_BUILT_LDS2014_GLOBE_R2018A_54009_250_V2_0_8_5.tif'

# GHS population shapefile
GHS_pop_filename = 'GHS_proj_2015Pop_250m_{placename}/GHS_proj_2015Pop_250m_{placename}.shp'.format(placename=placename)
GHS_pop_filepath = pop_folder + "/" + GHS_pop_filename

# # GHS built-up shapefile
GHS_builtup_filename = 'GHS_proj_2014builtup_250m_{studyregion}/GHS_proj_2014builtup_250m_{studyregion}.shp'.format(
        studyregion = placename)
GHS_builtup_filepath = OSM_folder + "/" + builtup_filename
