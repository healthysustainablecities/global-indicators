"""
Study region setup.

A wrapper script for deriving a study region's feature and network data from OpenStreetMap and other data sources to support subsequent indicator analyses.
"""
import os
import subprocess
import sys

import yaml

# Load study region configuration
from subprocesses._project_setup import (
    codename,
    folder_path,
    region_dir,
    regions,
)
from tqdm.auto import tqdm

if len(sys.argv) < 2:
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

# Create study region folder if not exists
if not os.path.exists(f'{folder_path}/process/data/_study_region_outputs'):
    os.makedirs(f'{folder_path}/process/data/_study_region_outputs')
if not os.path.exists(region_dir):
    os.makedirs(region_dir)

study_region_setup = {
    '_00_create_database.py': 'Create database',
    '_01_create_study_region.py': 'Create study region',
    '_02_create_osm_resources.py': 'Create OpenStreetMap resources',
    '_03_create_network_resources.py': 'Create pedestrian network',
    '_04_create_population_grid.py': 'Align population distribution',
    '_05_compile_destinations.py': 'Compile destinations',
    '_06_open_space_areas_setup.py': 'Identify public open space',
    '_07_locate_origins_destinations.py': 'Analyse local neighbourhoods',
    '_08_destination_summary.py': 'Summarise spatial distribution',
    '_09_urban_covariates.py': 'Collate urban covariates',
    '_10_gtfs_analysis.py': 'Analyse GTFS Feeds',
    '_11_export_gpkg.py': 'Export geopackage',
    '_12_neighbourhood_analysis.py': 'Analyse neighbourhoods',
    '_13_aggregation.py': 'Aggregate region summary analyses',
}
pbar = tqdm(study_region_setup, position=0, leave=True)
try:
    for step in pbar:
        pbar.set_description(study_region_setup[step])
        try:
            process = subprocess.Popen(
                f'python {step} {codename}',
                shell=True,
                cwd='./subprocesses',
                stderr=open(f'{region_dir}/_01_create_study_region.log', 'a'),
                stdout=open(f'{region_dir}/_01_create_study_region.log', 'a'),
            )
        except Exception as e:
            raise (f'Processing {step} failed: {e}')
        finally:
            process.wait()
except Exception as e:
    raise Exception(f'An error occurred: {e}')
finally:
    print(
        '\n\nOnce the setup of study region resources has been successfully completed, we encourage you to inspect the region-specific resources (either from the spatial database, or using the geopackage export file). \n\n',
    )
