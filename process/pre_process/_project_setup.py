# Script:  _project_setup.py
# Version: 2020-08-12
# Author:  Carl Higgs
#
# All scripts within the process folder draw on the parameters defined 
# in the configuration/config.yml and configuration/regions.yml files to 
# source and output resources. 
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
import yaml
import getpass

# import custom utility functions
from _utils import *

current_script = sys.argv[0]

import warnings
# filter out Geopandas RuntimeWarnings, due to geopandas/fiona read file spam
# https://stackoverflow.com/questions/64995369/geopandas-warning-on-read-file
warnings.filterwarnings("ignore",category=RuntimeWarning, module='geopandas')

# Set up locale (ie. defined at command line, or else testing)
if len(sys.argv) >= 2:
  locale = sys.argv[1]
else:
  locale = 'ghent_2022_v2'
  # sys.exit('Please supply a locale argument (see region_settings tab in config file)')

# cwd = os.path.join(os.getcwd(),'../process')
cwd = os.getcwd()
folder_path = os.path.abspath('../data')

# Load project configuration
with open('/home/jovyan/work/process/configuration/config.yml') as f:
     config = yaml.safe_load(f)

for group in config.keys():
  for var in config[group].keys():
    globals()[var]=config[group][var]

del config

# Load study region configuration
with open('/home/jovyan/work/process/configuration/regions.yml') as f:
     regions = yaml.safe_load(f)

for var in regions[locale].keys():
    globals()[var]=regions[locale][var]

regions = list(regions.keys())[1:]

# Load OpenStreetMap destination and open space parameters
df_osm_dest = pandas.read_csv(osm_destination_definitions)

with open('/home/jovyan/work/process/configuration/osm_open_space.yml') as f:
     open_space = yaml.safe_load(f)

for var in open_space.keys():
    globals()[var]=open_space[var]
    
del open_space

# derived study region name (no need to change!)
study_region = f'{locale}_{region}_{year}'.lower()
db = f'li_{locale}_{year}'.lower()

# region specific output locations
locale_dir = os.path.join(folder_path,'study_region',study_region)
locale_maps = os.path.join('../../maps/',study_region)

# Study region buffer
buffered_study_region = f'{study_region}_{study_buffer}{units}'

# sample points
points = f'{points}_{point_sampling_interval}m'

try:
    areas = {}
    areas['data'] = area_data
    licence = str(area_data_licence)
    if licence not in ['none specified','nan','']:
        licence_url = area_data_licence_url
        licence_attrib = f' under <a href=\"{licence_url}/\">{licence}</a>'
    else:
        licence_attrib = ''
    source_url  = area_data_source_url
    provider    = area_data_source
    areas['attribution'] = f'Boundary data: <a href=\"{source_url}/\">{provider}</a>{licence_attrib}'
except:
    print('Please check area data in project configuration: not all required areas of interest parameters appear to have been defined...(error:{})'.format(sys.exc_info()))
   
# Neighbourhood spatial distribution grid settings
hex_grid = f'{study_region}_hex_{hex_diag}{units}_diag'
hex_side = float(hex_diag)*0.5
hex_area_km2 = ((3*math.sqrt(3.0)/2)*(hex_side)**2)*10.0**-6
population_grid = f'population_{hex_diag}{units}_{population["year_target"]}'

# Database setup
dbComment = f'Liveability indicator data for {locale} {year}.'
os.environ['PGHOST']     = db_host
os.environ['PGPORT']     = str(db_port)
os.environ['PGUSER']     = db_user
os.environ['PGPASSWORD'] = db_pwd
os.environ['PGDATABASE'] = db

# OSM settings
osm_data = os.path.join(folder_path,osm['osm_data'])
osm_date = osm['osm_date']
osm_prefix = f'osm_{osm_date}'
osmnx_retain_all = osm['osmnx_retain_all']
osm_region = f'{locale}_{osm_prefix}.osm'
osm_source = os.path.join(folder_path,'study_region',locale,f'{buffered_study_region}_{osm_prefix}.osm')
             
grant_query = f'''GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {db_user};
                 GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {db_user};'''

# roads
# Define network data name structures
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
study_destinations = 'study_destinations'
df_osm_dest = df_osm_dest.replace(np.nan, 'NULL', regex=True)
covariate_list = ghsl_covariates['air_pollution'].keys()

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
 
def main():
    print(f'\n{authors}, Version {version}\n\nRegion code names for running scripts:\n\n{" ".join(regions)}\n\nCurrent default: {locale} ({full_locale})\n')
    return regions

if __name__ == '__main__':
    main()
else:
    print(f'\n{full_locale}\n')