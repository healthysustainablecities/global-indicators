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
    folder_path,
    locale,
    locale_dir,
    regions,
)
from tqdm.auto import tqdm

# Create study region folder if not exists
if not os.path.exists(f'{folder_path}/process/data/study_region'):
    os.makedirs(f'{folder_path}/process/data/study_region')
if not os.path.exists(locale_dir):
    os.makedirs(locale_dir)

study_region_setup = {
    '00_create_database.py': 'Create database',
    '01_create_study_region.py': 'Create study region',
    '02_create_osm_resources.py': 'Create OpenStreetMap resources',
    '03_create_network_resources.py': 'Create pedestrian network',
    '04_create_population_grid.py': 'Align population distribution',
    '05_compile_destinations.py': 'Compile destinations',
    '06_open_space_areas_setup.py': 'Identify public open space',
    '07_locate_origins_destinations.py': 'Analyse local neighbourhoods',
    '08_destination_summary.py': 'Summarise spatial distribution',
    '09_urban_covariates.py': 'Collate urban covariates',
    '10_gtfs_analysis.py': 'Analyse GTFS Feeds',
    '11_export_gpkg.py': 'Export geopackage',
    '12_neighbourhood_analysis.py': 'Analyse neighbourhoods',
    '13_aggregation.py': 'Aggregate summaries',
}
pbar = tqdm(study_region_setup, position=0, leave=True)
try:
    for step in pbar:
        pbar.set_description(study_region_setup[step])
        try:
            process = subprocess.Popen(
                f'python {step} {locale}',
                shell=True,
                cwd='./subprocesses',
                stderr=open(f'{locale_dir}/_01_create_study_region.log', 'a'),
                stdout=open(f'{locale_dir}/_01_create_study_region.log', 'a'),
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
