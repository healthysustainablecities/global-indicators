# Script:  _project_setup.py
# Version: 2020-08-12
# Author:  Carl Higgs
#
# All scripts within the process folder draw on the sources, parameters and modules
# specified in the file _project_configuration.xlsx to source and output 
# resources. 
#
# If you are starting a new project, you can set up the global parameters which 
# (pending overrides) should be applied for each study region in the 
#  detailed_explanation' folder.
#
# If you are adding a new study region to an existing project, this study region
# will be entered as a column within the 'Parameters' worksheet; the corresponding
# row entries must be completed as required.

# import modules
import os
import sys
import time
import pandas
import numpy as np
import subprocess as sp
import math 
import re

# import custom utility functions
from _utils import *

current_script = sys.argv[0]

# Set up locale (ie. defined at command line, or else testing)
if len(sys.argv) >= 2:
  locale = sys.argv[1]
else:
  locale = 'adelaide'
  # sys.exit('Please supply a locale argument (see region_settings tab in config file)')
if __name__ == '__main__':
  print(f"\nProcessing script {current_script} for locale {locale}...\n")

# cwd = os.path.join(os.getcwd(),'../process')
cwd = os.getcwd()
folder_path = os.path.abspath('../data')

# Load settings from _project_configuration.xlsx
xls = pandas.ExcelFile(os.path.join(cwd,'_project_configuration.xlsx'))
df_global = pandas.read_excel(xls, 'project_settings',index_col=0)
df_local = pandas.read_excel(xls, 'region_settings',index_col=0)
# df_osm = pandas.read_excel(xls, 'osm_and_open_space_defs')
df_os = pandas.read_excel(xls, 'osm_open_space').set_index('variable')
df_osm_dest = pandas.read_excel(xls, 'osm_dest_definitions')
df_datasets = pandas.read_excel(xls, 'datasets')
df_destinations = pandas.read_excel(xls, 'destinations')

# prepare and clean configuration entries
for var in [x for x in  df_global.index.values]:
    globals()[var] = df_global.loc[var]['parameters']

df_local[locale] = df_local[locale].fillna('')
for var in [x for x in  df_local.index.values]:
    globals()[var] = df_local.loc[var][locale]
# full_locale = df_parameters.loc['full_locale'][locale]
df_datasets.name_s = df_datasets.name_s.fillna('')
df_datasets = df_datasets.query(f' purpose == "{population_data}" | purpose == "{urban_data}"')
df_datasets.set_index('name_s',inplace=True)

# derived study region name (no need to change!)
study_region = f'{locale}_{region}_{year}'.lower()
db = f'li_{locale}_{year}'.lower()

print(f'\n{full_locale}\n')

# define areas for global indicators project (not undertaken at multiple administrative scales; filling in some fixed parameters)
analysis_scale = 'city'
area = analysis_scale
area_ids = ''
area_display_bracket = ''

# region specific output locations
locale_dir = os.path.join(folder_path,'study_region',study_region)
locale_maps = os.path.join('../../maps/',study_region)

# Study region buffer
buffered_study_region = f'{study_region}_{study_buffer}{units}'

# sample points
points = f'{points}_{point_sampling_interval}m'
urban_region =  str(df_datasets.loc[urban_data,'data_dir'])
if urban_region not in ['','nan']:
  urban_region = os.path.join('..',urban_region)

try:
    areas = {}
    areas[area] = {}
    # areas[area]['data'] = df_datasets[df_datasets.index== area_meta['area_datasets'][idx]].data_dir.values[0]
    areas[area]['data'] = area_data
    areas[area]['name'] = area.title()
    areas[area]['table'] = re.sub('[^\s\w]+', '', areas[area]['name']).lower().strip().replace(' ','_')
    areas[area]['display_main'] = areas[area]['name']
    licence = str(area_data_licence)
    if licence not in ['none specified','nan','']:
        licence_url = area_data_licence_url
        licence_attrib = f' under <a href=\"{licence_url}/\">{licence}</a>'
    else:
        licence_attrib = ''
    source_url  = area_data_source_url
    provider    = area_data_source
    areas[area]['attribution'] = f'Boundary data: <a href=\"{source_url}/\">{provider}</a>{licence_attrib}'
except:
    print('Please check area data in project configuration: not all required areas of interest parameters appear to have been defined...(error:{})'.format(sys.exc_info()))

analysis_field = areas[area]['name']
   
# Derived hex settings
hex_grid = f'{study_region}_hex_{hex_diag}{units}_diag'
hex_grid_buffer =  f'{study_region}_hex_{hex_diag}{units}_diag_{hex_buffer}{units}_buffer'
hex_side = float(hex_diag)*0.5
hex_area_km2 = ((3*math.sqrt(3.0)/2)*(hex_side)**2)*10.0**-6

hex_grid_100m = f'{study_region}_hex_100{units}_diag'
hex_side_100 = float(100)*0.5
hex_area_km2_100_diag = ((3*math.sqrt(3.0)/2)*(hex_side_100)**2)*10.0**-6

hex_grid_250m = f'{study_region}_hex_250{units}_diag'
hex_side_250 = float(250)*0.5
hex_area_km2_250_diag = ((3*math.sqrt(3.0)/2)*(hex_side_250)**2)*10.0**-6

# Database names -- derived from above parameters; (no need to change!)
dbComment = f'Liveability indicator data for {locale} {year}.'

# Environment settings for SQL
os.environ['PGHOST']     = db_host
os.environ['PGPORT']     = str(db_port)
os.environ['PGUSER']     = db_user
os.environ['PGPASSWORD'] = db_pwd
os.environ['PGDATABASE'] = db

# OSM settings
osm_data = os.path.join(folder_path,osm_data)
osm_date = str(osm_date)
osm_prefix = f'osm_{osm_date}'
osm_region = f'{locale}_{osm_prefix}.osm'

osm_source = os.path.join(folder_path,'study_region',locale,f'{buffered_study_region}_{osm_prefix}.osm')

# define pedestrian network custom filter (based on OSMnx 'walk' network type, without the cycling exclusion)
pedestrian = (
             '["highway"]'
             '["area"!~"yes"]' 
             '["highway"!~"motor|proposed|construction|abandoned|platform|raceway"]'
             '["foot"!~"no"]'  
             '["service"!~"private"]' 
             '["access"!~"private"]'
             )
             
grant_query = f'''GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {db_user};
                 GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {db_user};'''

# roads
# Define network data name structures
# road_data = df_parameters.loc['road_data'][locale]  # the folder where road data is kept
network_folder = f'osm_{buffered_study_region}_epsg{srid}_pedestrian_{osm_prefix}'
network_source = os.path.join(locale_dir,network_folder)
intersections_table = f"clean_intersections_{intersection_tolerance}m"

# Sausage buffer run parameters
# If you experience 'no forward edges' issues, change this value to 1
# this means that for *subsequently processed* buffers, it will use 
# an ST_SnapToGrid parameter of 0.01 instead of 0.001
## The first pass should use 0.001, however.
snap_to_grid = 0.001
if no_forward_edge_issues == 1:
  snap_to_grid = 0.01

# Destinations data directory
# dest_dir = os.path.join(folder_path,dest_dir)
study_destinations = 'study_destinations'

# array / list of destinations 
# IMPORTANT -- These are specified in the 'destinations' worksheet of the _project_configuration.xlsx file
#               - specify: destination, domain, cutoff and count distances as required
#
#           -- If new destinations are added, they should be appended to end of list 
#              to ensure this order is respected across time.
#
# The table 'dest_type' will be created in Postgresql to keep track of destinations

df_destinations = df_destinations.replace(np.nan, 'NULL', regex=True)
destination_list = [x for x in df_destinations.destination.tolist()] # the destinations 

df_osm_dest = df_osm_dest.replace(np.nan, 'NULL', regex=True)

# Colours for presenting maps
colours = {}
# http://colorbrewer2.org/#type=qualitative&scheme=Dark2&n=8
colours['qualitative'] = ['#1b9e77','#d95f02','#7570b3','#e7298a','#66a61e','#e6ab02','#a6761d','#666666']
# http://colorbrewer2.org/#type=diverging&scheme=PuOr&n=8
colours['diverging'] = ['#8c510a','#bf812d','#dfc27d','#f6e8c3','#c7eae5','#80cdc1','#35978f','#01665e']
        
map_style = '''
<style>
.legend {
    padding: 0px 0px;
    font: 12px sans-serif;
    background: white;
    background: rgba(255,255,255,1);
    box-shadow: 0 0 15px rgba(0,0,0,0.2);
    border-radius: 5px;
    }
.leaflet-control-attribution {
	width: 60%;
	height: auto;
	}
.leaflet-container {
    background-color:rgba(255,0,0,0.0);
}
</style>
<script>L_DISABLE_3D = true;</script>
'''    

# specify that the above modules and all variables below are imported on 'from config.py import *'
__all__ = [x for x in dir() if x not in ['__file__','__all__', '__builtins__', '__doc__', '__name__', '__package__']]
 
