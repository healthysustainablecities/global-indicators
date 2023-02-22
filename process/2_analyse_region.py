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
