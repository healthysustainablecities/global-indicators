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
import pandas as pd
import yaml

current_script = sys.argv[0]

# Allow for project setup to run from different directories; potentially outside docker
# This means project configuration and set up can be verified in externally launched tests
if os.path.exists(f'{os.getcwd()}/../global-indicators.sh'):
    folder_path = os.path.abspath(f'{os.getcwd()}/../')
    sys.path.append(os.path.abspath('./subprocesses'))
elif os.path.exists(f'{os.getcwd()}/../../global-indicators.sh'):
    folder_path = os.path.abspath(f'{os.getcwd()}/../../')
    sys.path.append(os.path.abspath('.'))
else:
    folder_path = os.getcwd()

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


# Set up region data
def region_data_setup(
    region, region_config, data, data_path=None,
):
    """Check data configuration for regions and make paths absolute."""
    try:
        if data not in datasets or datasets[data] is None:
            raise SystemExit(
                f'\nAn entry for at least one {data} dataset does not appear to have been defined in datasets.yml.  This parameter is required for analysis, and is used to cross-reference a relevant dataset defined in datasets.yml with region configuration in {region}.yml.  Please update datasets.yml to proceed.\n',
            )
        elif region_config[data] is None:
            raise SystemExit(
                f'\nThe entry for {data} does not appear to have been defined in {region}.yml.  This parameter is required for analysis, and is used to cross-reference a relevant dataset defined in datasets.yml.  Please update {region}.yml to proceed.\n',
            )
        elif datasets[data][region_config[data]] is None:
            raise SystemExit(
                f'\nThe configured entry for {region_config[data]} under {data} within datasets.yml does not appear to be associated within any values.  Please check and amend the specification for this entry within datasets.yml , or the configuration within {region}.yml to proceed. (is this entry and its records indented as per the provided example?)\n',
            )
        else:
            if 'citation' not in datasets[data][region_config[data]]:
                if data != 'OpenStreetMap':
                    raise SystemExit(
                        f'\nNo citation record has been configured for the {data} dataset configured for this region.  Please add this to its record in datasets.yml (see template datasets.yml for examples).\n',
                    )
                elif 'source' not in region_config['OpenStreetMap']:
                    datasets[data][region_config[data]][
                        'citation'
                    ] = f'OpenStreetMap Contributors ({str(datasets[data][region_config[data]]["publication_date"])[:4]}). {datasets[data][region_config[data]]["url"]}'
                else:
                    datasets[data][region_config[data]][
                        'citation'
                    ] = f'OpenStreetMap Contributors.  {datasets[data][region_config[data]]["source"]} ({str(datasets[data][region_config[data]]["publication_date"])[:4]}). {datasets[data][region_config[data]]["url"]}'
            data_dictionary = datasets[data][region_config[data]].copy()
        if ('data_dir' not in data_dictionary) or (
            data_dictionary['data_dir'] is None
        ):
            raise SystemExit(
                f"The 'data_dir' entry for {data} does not appear to have been defined in datasets.yml.  This parameter is required for analysis of {region}, and is used to locate a required dataset cross-referenced in {region}.yml.  Please update datasets.yml to proceed.",
            )
        if data_path is not None:
            data_dictionary[
                'data_dir'
            ] = f"{data_path}/{datasets[data][region_config[data]]['data_dir']}"
        return data_dictionary
    except Exception as e:
        raise e


def verify_data_dir(data_dir, verify_file_extension=None):
    """Return true if supplied data directory exists, optionally checking for existance of at least one file matching a specific extension within that directory."""
    if verify_file_extension is None:
        return os.path.exists(data_dir)
        # If False: f'The configured file in datasets.yml could not be located at {data_dir}.  Please check file and configuration of datasets.yml.',
    else:
        return any(
            File.endswith(verify_file_extension)
            for File in os.listdir(data_dir)
        )
        # If False: f"A file having extension '{verify_file_extension}' could not be located within {data_dir}.  Please check folder contents and configuration of datasets.yml."


def region_dictionary_setup(region, region_config, config, folder_path):
    r = region_config.copy()
    date = time.strftime('%Y-%m-%d')
    r['study_region'] = region
    study_buffer = config['project']['study_buffer']
    units = config['project']['units']
    buffered_urban_study_region = f'urban_study_region_{study_buffer}{units}'
    r['crs_srid'] = f"{r['crs']['standard']}:{r['crs']['srid']}"
    r[
        'osm_prefix'
    ] = f"osm_{datasets['OpenStreetMap'][r['OpenStreetMap']]['publication_date']}"
    r[
        'region_dir'
    ] = f'{folder_path}/process/data/_study_region_outputs/{r["study_region"]}'
    data_path = f'{folder_path}/process/data'
    if r['study_region_boundary']['data'] != 'urban_query':
        r['study_region_boundary'][
            'data'
        ] = f"{data_path}/{r['study_region_boundary']['data']}"
    r['urban_region'] = region_data_setup(
        region, region_config, 'urban_region', data_path,
    )
    r['buffered_urban_study_region'] = buffered_urban_study_region
    r['db'] = region.lower()
    r['dbComment'] = f'Liveability indicator data for {region} {r["year"]}.'
    r['population'] = region_data_setup(
        region, region_config, 'population', data_path,
    )
    resolution = r['population']['resolution'].replace(' ', '')
    r['population'][
        'crs_srid'
    ] = f'{r["population"]["crs_standard"]}:{r["population"]["crs_srid"]}'
    r[
        'population_grid'
    ] = f'population_{resolution}_{r["population"]["year_target"]}'
    r['OpenStreetMap'] = region_data_setup(
        region, region_config, 'OpenStreetMap', data_path,
    )
    r['OpenStreetMap'][
        'osm_region'
    ] = f'{r["region_dir"]}/{region}_{r["osm_prefix"]}.pbf'
    r['codename_poly'] = f'{r["region_dir"]}/poly_{r["db"]}.poly'
    r[
        'intersections_table'
    ] = f"clean_intersections_{r['network']['intersection_tolerance']}m"
    r[
        'gpkg'
    ] = f'{r["region_dir"]}/{r["study_region"]}_{study_buffer}m_buffer.gpkg'
    r['point_summary'] = f'{r["study_region"]}_sample_points'
    r['grid_summary'] = f'{r["study_region"]}_grid_{resolution}'
    r['city_summary'] = f'{r["study_region"]}_region'
    if 'policy_review' in r:
        r['policy_review'] = f"{folder_path}/{r['policy_review']}"
    else:
        r['policy_review'] = None
    if r['network']['buffered_region']:
        r[
            'graphml'
        ] = f'{r["region_dir"]}/{r["study_region"]}_{study_buffer}m_pedestrian_{r["osm_prefix"]}.graphml'
        r[
            'graphml_proj'
        ] = f'{r["region_dir"]}/{r["study_region"]}_{study_buffer}m_pedestrian_{r["osm_prefix"]}_proj.graphml'
    else:
        r[
            'graphml'
        ] = f'{r["region_dir"]}/{r["study_region"]}_pedestrian_{r["osm_prefix"]}.graphml'
        r[
            'graphml_proj'
        ] = f'{r["region_dir"]}/{r["study_region"]}_pedestrian_{r["osm_prefix"]}_proj.graphml'
    return r


# Load project configuration files
config_path = f'{folder_path}/process/configuration'
if os.path.isfile(f'{config_path}/config.yml'):
    load_yaml(
        f'{config_path}/config.yml', unnest=True, unnest_level=2,
    )
else:
    raise Exception(
        "\n\nProject configuration file couldn't be located at process/configuration/config.yml.  Please ensure project has been initialised and configured before commencing analysis.\n\n",
    )

load_yaml(f'{config_path}/datasets.yml', unnest=True)
load_yaml(f'{config_path}/osm_open_space.yml', unnest=True)
load_yaml(f'{config_path}/indicators.yml')
load_yaml(f'{config_path}/policies.yml')
region_names = [
    x.split('.yml')[0]
    for x in os.listdir(f'{config_path}/regions')
    if x.endswith('.yml')
]

# Set up date and time
os.environ['TZ'] = analysis_timezone
time.tzset()
date = time.strftime('%Y-%m-%d')
date_hhmm = time.strftime('%Y-%m-%d_%H%M')

# Load OpenStreetMap destination and open space parameters
df_osm_dest = pd.read_csv(
    f'{config_path}/osm_destination_definitions.csv',
).replace(np.nan, 'NULL', regex=True)

# Set up codename (ie. defined at command line, or else testing)
is_default_codename = ''
if any(
    [
        os.path.basename(f.filename).startswith('test_')
        for f in inspect.stack()[1:]
    ],
):
    codename = default_codename
elif len(sys.argv) >= 2:
    codename = sys.argv[1]
elif any(['2_analyse_region.py' in f.filename for f in inspect.stack()[1:]]):
    sys.exit(
        f'\n{authors}, version {version}\n\n'
        'This script requires a study region code name corresponding to .yml files '
        'in configuration/regions be provided as an argument.  '
        'For example, for Las Palmas de Gran Canaria, Spain (the provided example):\n\n'
        'python 1_create_project_configuration_files\n'
        'python 1_create_project_configuration_files example_ES_Las_Palmas_2023\n'
        'python 2_analyse_region.py example_ES_Las_Palmas_2023\n'
        'python 3_generate_resources.py example_ES_Las_Palmas_2023\n\n'
        f'The code names for currently configured regions are {region_names}\n',
    )
elif default_codename in region_names:
    codename = default_codename
    is_default_codename = '; configured as default in config.yml'
else:
    sys.exit(
        f'\n{authors}, version {version}\n\n'
        'This script requires a study region code name corresponding to .yml files '
        'in configuration/regions be provided as an argument.  '
        'For example, for Las Palmas de Gran Canaria, Spain (the provided example):\n\n'
        'python 1_create_project_configuration_files\n'
        'python 1_create_project_configuration_files example_ES_Las_Palmas_2023\n'
        'python 2_analyse_region.py example_ES_Las_Palmas_2023\n'
        'python 3_generate_resources.py example_ES_Las_Palmas_2023\n\n'
        f'The code names for currently configured regions are {region_names}\n',
    )

# Data set up for region
try:
    load_yaml(f'{config_path}/regions/{codename}.yml', name='region_config')
except Exception as e:
    sys.exit(
        f'\n\nError: {e}\n\nLoading of study region configuration file for the specified city codename failed.  Please confirm that configuration has been completed for this city (e.g. editing the file configuration/regions/{codename}.yml in a text editor), consulting the provided example configuration files as required.\n\nFurther assistance may be requested by logging an issue at:\nhttps://github.com/global-healthy-liveable-cities/global-indicators/issues\n\n',
    )

region_config = region_dictionary_setup(
    codename, region_config, config, folder_path,
)


# Add region variables for this study region to global variables
for var in region_config.keys():
    globals()[var] = region_config[var]

# Check configured data exists for this specified region
assert verify_data_dir(urban_region['data_dir'], verify_file_extension=None)
assert verify_data_dir(OpenStreetMap['data_dir'], verify_file_extension=None)
assert verify_data_dir(population['data_dir'], verify_file_extension='tif')
if study_region_boundary['data'] != 'urban_query':
    assert verify_data_dir(study_region_boundary['data'].split(':')[0])

# sample points
points = f'{points}_{point_sampling_interval}m'

# Database setup
os.environ['PGHOST'] = db_host
os.environ['PGPORT'] = str(db_port)
os.environ['PGUSER'] = db_user
os.environ['PGPASSWORD'] = db_pwd
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
        f'\n{authors}, version {version}\n\nRegion code names for running scripts:\n\n{" ".join(region_names)}\n\nCurrent default: {name} ({codename}{is_default_codename})\n',
    )
    return region_names


if __name__ == '__main__':
    main()
else:
    print(f'\n{authors}, version {version}')
    print(f'\n{name} ({codename}{is_default_codename})')
    print(
        f"\nOutput directory:\n  {region_dir.replace('/home/ghsci/work/','')}\n",
    )
