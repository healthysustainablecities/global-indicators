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
import math 
import yaml
import getpass

current_script = sys.argv[0]
date = time.strftime("%Y-%m-%d")

import warnings
# filter out Geopandas RuntimeWarnings, due to geopandas/fiona read file spam
# https://stackoverflow.com/questions/64995369/geopandas-warning-on-read-file
warnings.filterwarnings("ignore",category=RuntimeWarning, module='geopandas')

# Load project configuration
with open('/home/jovyan/work/process/configuration/config.yml') as f:
    config = yaml.safe_load(f)
    config_description = config.pop('description',None)

for group in config.keys():
  for var in config[group].keys():
    globals()[var]=config[group][var]

del config

# Load study region configuration
with open('/home/jovyan/work/process/configuration/regions.yml') as f:
    regions = yaml.safe_load(f)
    region_description = regions.pop('description',None)
    region_names = list(regions.keys())[1:]

# Set up locale (ie. defined at command line, or else testing)
if len(sys.argv) >= 2:
  locale = sys.argv[1]
else:
    locale = 'manchester'
  # sys.exit(
  # f"\n{authors}, version {version}\n\n"
   # "This script requires a study region code name corresponding to definitions "
   # "in configuration/regions.yml be provided as an argument (lower case, with "
   # "spaces instead of underscores).  For example, for Hong Kong:\n\n"
   # "python 01_study_region_setup.py hong_kong\n"
   # "python 02_neighbourhood_analysis.py hong_kong\n"
   # "python 03_aggregation.py hong_kong\n\n"
  # f"The code names for currently configured regions are {region_names}\n"
  # )

with open('/home/jovyan/work/process/configuration/datasets.yml') as f:
     datasets = yaml.safe_load(f)

for var in datasets.keys():
    globals()[var]=datasets[var]

# Load OpenStreetMap destination and open space parameters
df_osm_dest = pandas.read_csv(osm_destination_definitions)

with open('/home/jovyan/work/process/configuration/osm_open_space.yml') as f:
     open_space = yaml.safe_load(f)

for var in open_space.keys():
    globals()[var]=open_space[var]

del open_space

# Load definitions of measures and indicators
with open('/home/jovyan/work/process/configuration/indicators.yml') as f:
     indicators = yaml.safe_load(f)

# sample points
points = f'{points}_{point_sampling_interval}m'
population_density = "sp_local_nh_avg_pop_density"
intersection_density = "sp_local_nh_avg_intersection_density"

# Database setup
os.environ['PGHOST']     = db_host
os.environ['PGPORT']     = str(db_port)
os.environ['PGUSER']     = db_user
os.environ['PGPASSWORD'] = db_pwd

# Destinations data directory
study_destinations = 'study_destinations'
df_osm_dest = df_osm_dest.replace(np.nan, 'NULL', regex=True)
covariate_list = ghsl_covariates['air_pollution'].keys()

# outputs
resolution = population[regions[locale]["population"]]['resolution'].replace(' ','')
gpkg_output_grid = f'{output_folder}/global_indicators_grid_{resolution}{units}_{date}.gpkg'
gpkg_output_cities = f'{output_folder}/global_indicators_city_{date}.gpkg'

# Data set up for region

for r in regions:
    year = regions[r]['year']
    study_region = f"{r}_{regions[r]['region']}_{year}".lower()
    buffered_study_region = f'{study_region}_{study_buffer}{units}'
    crs = f"{regions[r]['crs_standard']}:{regions[r]['crs_srid']}"
    osm_prefix = f"osm_{OpenStreetMap[regions[r]['OpenStreetMap']]['osm_date']}"
    intersection_tolerance = regions[r]['intersection_tolerance']
    locale_dir = os.path.join(folderPath,'study_region',study_region)
    population[regions[r]["population"]]['resolution'] = population[regions[r]["population"]]['resolution'].replace(' ','')
    regions[r]['crs'] = crs
    regions[r]['srid'] = regions[r]['crs_srid']
    regions[r]['locale_dir'] = locale_dir
    regions[r]['study_region'] = study_region
    regions[r]['buffered_study_region'] = buffered_study_region
    regions[r]['db'] = f'li_{r}_{year}'.lower()
    regions[r]['dbComment'] = f'Liveability indicator data for {r} {year}.'
    regions[r]['population'] = population[regions[r]["population"]]
    regions[r]['population']['crs'] = f'{regions[r]["population"]["crs_standard"]}:{regions[r]["population"]["crs_srid"]}'
    regions[r]['population_grid'] = f'population_{resolution}_{regions[r]["population"]["year_target"]}'
    regions[r]['osm_data'] = f'{folderPath}/{OpenStreetMap[regions[r]["OpenStreetMap"]]["osm_data"]}'
    regions[r]['osm_prefix'] = osm_prefix
    regions[r]['osm_region'] = f'{r}_{osm_prefix}.osm'
    regions[r]['osm_source'] = f"{locale_dir}/{buffered_study_region}_{osm_prefix}.osm"
    regions[r]['network_folder'] = f'osm_{buffered_study_region}_{crs}_pedestrian_{osm_prefix}'
    regions[r]['intersections_table'] = f"clean_intersections_{intersection_tolerance}m"
    regions[r]['network_source'] = os.path.join(locale_dir,regions[r]['network_folder'])
    regions[r]['gpkg'] = f"{locale_dir}/{study_region}_{study_buffer}m_buffer.gpkg"
    regions[r]['grid_summary'] = f"{study_region}_grid_{resolution}m_{date}"
    regions[r]['city_summary'] = f"{study_region}_city_{date}"
    if regions[r]['network_not_using_buffered_region']:
        regions[r]['graphml'] = f"{locale_dir}/{study_region}_pedestrian_{osm_prefix}.graphml"
        regions[r]['graphml_proj'] = f"{locale_dir}/{study_region}_pedestrian_{osm_prefix}_proj.graphml"
    else: 
        regions[r]['graphml'] = f"{locale_dir}/{study_region}_{study_buffer}m_pedestrian_{osm_prefix}.graphml"
        regions[r]['graphml_proj'] = f"{locale_dir}/{study_region}_{study_buffer}m_pedestrian_{osm_prefix}_proj.graphml"

# Add region variables for this study region to global variables
for var in regions[locale].keys():
    globals()[var]=regions[locale][var]   


os.environ['PGDATABASE'] = db

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

grant_query = f'''GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {db_user};
                 GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {db_user};'''

# specify that the above modules and all variables below are imported on 'from config.py import *'
__all__ = [x for x in dir() if x not in ['__file__','__all__', '__builtins__', '__doc__', '__name__', '__package__']]
 
def main():
    print(f'\n{authors}, version {version}\n\nRegion code names for running scripts:\n\n{" ".join(region_names)}\n\nCurrent default: {locale} ({full_locale})\n')
    return region_names

if __name__ == '__main__':
    main()
else:
    print(f"\n{authors}, version {version}\n\nProcessing: {full_locale}\n\n")