"""
Project setup.

Initialise parameters according to project, data and study region
configuration.

All scripts within the process folder draw on the parameters defined in
the configuration/config.yml and configuration/regions.yml files to
source and output resources.
"""

import inspect

# import modules
import os
import sys
import time
import warnings

import numpy as np
import pandas
import yaml

current_script = sys.argv[0]
date = time.strftime('%Y-%m-%d')

# Allow for project setup to run from different directories; potentially outside docker
# This means project configuration and set up can be verified in externally launched tests
if os.path.exists(f'{os.getcwd()}/../global-indicators.sh'):
    folder_path = os.path.abspath(f'{os.getcwd()}/../')
elif os.path.exists(f'{os.getcwd()}/../../global-indicators.sh'):
    folder_path = os.path.abspath(f'{os.getcwd()}/../../')
else:
    folder_path = os.get_cwd()

# filter out Geopandas RuntimeWarnings, due to geopandas/fiona read file spam
# https://stackoverflow.com/questions/64995369/geopandas-warning-on-read-file
warnings.filterwarnings('ignore', category=RuntimeWarning, module='geopandas')
# Ignore warning from pandana 0.6.1 with pandas 1.5.2 regarding empty Series (a call to pd.Series())
# This message is repeated multiple times, and is not currently an issue with our package.
warnings.filterwarnings(
    'ignore',
    message=r"The default dtype for empty Series will be 'object' instead of 'float64' in a future version.",
    category=FutureWarning,
    module='pandana',
)


# Load configuration files
def load_yaml(
    yml, name=None, unnest=False, unnest_level=1, remove=False, describe=True,
):
    if name is None:
        # try to use the filename as variable name
        name = yml.split('/')[-1].split('.')[0]
    with open(yml) as f:
        globals()[name] = yaml.safe_load(f)
    if describe:
        if 'description' in globals()[name]:
            # remove description from yaml, if present, storing for reference
            globals()[f'{name}_description'] = globals()[name].pop(
                'description', None,
            )
    if unnest:
        if unnest_level == 1:
            for var in globals()[name]:
                globals()[var] = globals()[name][var]
        elif unnest_level == 2:
            for group in globals()[name]:
                for var in globals()[name][group]:
                    globals()[var] = globals()[name][group][var]
        else:
            print(
                'Unnest was set to True, but unnest_level was not set to 1 or 2; skipping.',
            )
        if remove:
            del globals()[name]


# Load project configuration files
config_path = f'{folder_path}/process/configuration'
load_yaml(
    f'{config_path}/config.yml', unnest=True, unnest_level=2, remove=True,
)
load_yaml(f'{config_path}/regions.yml')
load_yaml(f'{config_path}/datasets.yml', unnest=True, remove=False)
load_yaml(f'{config_path}/osm_open_space.yml', unnest=True)
load_yaml(f'{config_path}/indicators.yml')
load_yaml(f'{config_path}/policies.yml')
region_names = list(regions.keys())

# Load OpenStreetMap destination and open space parameters
df_osm_dest = pandas.read_csv(f'{config_path}/osm_destination_definitions.csv')

# make relative pathsfrom configuration files absolute from folder_path
urban_region['data_dir'] = f'{folder_path}/{urban_region["data_dir"]}'
# Set up locale (ie. defined at command line, or else testing)
if any(['_generate_reports.py' in f.filename for f in inspect.stack()[1:]]):
    if '--city' in sys.argv:
        locale = sys.argv[sys.argv.index('--city') + 1]
    else:
        if len(sys.argv) >= 2:
            locale = sys.argv[1]
        else:
            locale = default_locale
        sys.argv = sys.argv + ['--city', locale]
elif any(
    [
        os.path.basename(f.filename).startswith('test_')
        for f in inspect.stack()[1:]
    ],
):
    locale = default_locale
elif len(sys.argv) >= 2:
    locale = sys.argv[1]
elif default_locale in region_names:
    locale = default_locale
else:
    sys.exit(
        f'\n{authors}, version {version}\n\n'
        'This script requires a study region code name corresponding to definitions '
        'in configuration/regions.yml be provided as an argument (lower case, with '
        'spaces instead of underscores).  For example, for Hong Kong:\n\n'
        'python 01_study_region_setup.py hong_kong\n'
        'python 02_neighbourhood_analysis.py hong_kong\n'
        'python 03_aggregation.py hong_kong\n\n'
        f'The code names for currently configured regions are {region_names}\n',
    )

# sample points
points = f'{points}_{point_sampling_interval}m'
population_density = 'sp_local_nh_avg_pop_density'
intersection_density = 'sp_local_nh_avg_intersection_density'

# Database setup
os.environ['PGHOST'] = db_host
os.environ['PGPORT'] = str(db_port)
os.environ['PGUSER'] = db_user
os.environ['PGPASSWORD'] = db_pwd

# Destinations data directory
study_destinations = 'study_destinations'
df_osm_dest = df_osm_dest.replace(np.nan, 'NULL', regex=True)
covariate_list = ghsl_covariates['air_pollution'].keys()

# Data set up for region
for r in regions:
    year = regions[r]['year']
    study_region = f"{r}_{regions[r]['region']}_{year}".lower()
    buffered_urban_study_region = f'urban_study_region_{study_buffer}{units}'
    crs = f"{regions[r]['crs_standard']}:{regions[r]['crs_srid']}"
    osm_prefix = (
        f"osm_{OpenStreetMap[regions[r]['OpenStreetMap']]['osm_date']}"
    )
    intersection_tolerance = regions[r]['intersection_tolerance']
    locale_dir = f'{folder_path}/process/data/study_region/{study_region}'
    resolution = population[regions[r]['population']]['resolution'].replace(
        ' ', '',
    )
    regions[r]['crs'] = crs
    regions[r]['srid'] = regions[r]['crs_srid']
    regions[r]['locale_dir'] = locale_dir
    regions[r]['study_region'] = study_region
    regions[r]['buffered_urban_study_region'] = buffered_urban_study_region
    regions[r]['db'] = f'li_{r}_{year}'.lower()
    regions[r]['dbComment'] = f'Liveability indicator data for {r} {year}.'
    regions[r]['population'] = population[regions[r]['population']]
    regions[r]['population'][
        'crs'
    ] = f'{regions[r]["population"]["crs_standard"]}:{regions[r]["population"]["crs_srid"]}'
    regions[r][
        'population_grid'
    ] = f'population_{resolution}_{regions[r]["population"]["year_target"]}'
    regions[r][
        'osm_data'
    ] = f'{folder_path}/process/data/{OpenStreetMap[regions[r]["OpenStreetMap"]]["osm_data"]}'
    regions[r]['osm_prefix'] = osm_prefix
    regions[r]['osm_region'] = f'{r}_{osm_prefix}.osm'
    regions[r][
        'osm_source'
    ] = f'{locale_dir}/{study_region}_{study_buffer}{units}_{osm_prefix}.osm'
    regions[r][
        'network_folder'
    ] = f'osm_{study_region}_{study_buffer}{units}_{crs}_pedestrian_{osm_prefix}'
    regions[r][
        'intersections_table'
    ] = f'clean_intersections_{intersection_tolerance}m'
    regions[r]['network_source'] = os.path.join(
        locale_dir, regions[r]['network_folder'],
    )
    regions[r][
        'gpkg'
    ] = f'{locale_dir}/{study_region}_{study_buffer}m_buffer.gpkg'
    regions[r]['grid_summary'] = f'{study_region}_grid_{resolution}m_{date}'
    regions[r]['city_summary'] = f'{study_region}_city_{date}'
    if 'policy_review' in regions[r]:
        regions[r][
            'policy_review'
        ] = f"{folder_path}/{regions[r]['policy_review']}"
    else:
        regions[r]['policy_review'] = 'Not configured'
    if regions[r]['network_not_using_buffered_region']:
        regions[r][
            'graphml'
        ] = f'{locale_dir}/{study_region}_pedestrian_{osm_prefix}.graphml'
        regions[r][
            'graphml_proj'
        ] = f'{locale_dir}/{study_region}_pedestrian_{osm_prefix}_proj.graphml'
    else:
        regions[r][
            'graphml'
        ] = f'{locale_dir}/{study_region}_{study_buffer}m_pedestrian_{osm_prefix}.graphml'
        regions[r][
            'graphml_proj'
        ] = f'{locale_dir}/{study_region}_{study_buffer}m_pedestrian_{osm_prefix}_proj.graphml'

# Add region variables for this study region to global variables
for var in regions[locale].keys():
    globals()[var] = regions[locale][var]

os.environ['PGDATABASE'] = db
# SQL alchemy >= 1.4 warns about planned deprecations in version 2
# however, Pandas / Geopandas doesn't yet support the new syntax
# and migration of syntax is not straightforward
# (warnings are obscure); hence ignoring warnings
# and pinning sqlalchemy < 2.0
os.environ['SQLALCHEMY_SILENCE_UBER_WARNING'] = '1'

# Colours for presenting maps
colours = {}
# http://colorbrewer2.org/#type=qualitative&scheme=Dark2&n=8
colours['qualitative'] = [
    '#1b9e77',
    '#d95f02',
    '#7570b3',
    '#e7298a',
    '#66a61e',
    '#e6ab02',
    '#a6761d',
    '#666666',
]
# http://colorbrewer2.org/#type=diverging&scheme=PuOr&n=8
colours['diverging'] = [
    '#8c510a',
    '#bf812d',
    '#dfc27d',
    '#f6e8c3',
    '#c7eae5',
    '#80cdc1',
    '#35978f',
    '#01665e',
]

map_style = """
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
"""

grant_query = f"""GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {db_user};
                 GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {db_user};"""

# specify that the above modules and all variables below are imported on 'from config.py import *'
__all__ = [
    x
    for x in dir()
    if x
    not in [
        '__file__',
        '__all__',
        '__builtins__',
        '__doc__',
        '__name__',
        '__package__',
    ]
]


def main():
    print(
        f'\n{authors}, version {version}\n\nRegion code names for running scripts:\n\n{" ".join(region_names)}\n\nCurrent default: {locale} ({full_locale})\n',
    )
    return region_names


if __name__ == '__main__':
    main()
else:
    print(f'\n{authors}, version {version}')
    if any(
        ['_generate_reports.py' in f.filename for f in inspect.stack()[1:]],
    ):
        print('\nGenerate reports\n')
    else:
        print(f'\nProcessing: {full_locale} ({locale})\n\n')
