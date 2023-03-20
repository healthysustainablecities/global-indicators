"""
Study region setup.

A wrapper script for deriving a study region's feature and network data from OpenStreetMap and other data sources to support subsequent indicator analyses.
"""
import os
import shutil
import subprocess
import sys

import yaml

# Load study region configuration
from subprocesses._project_setup import (
    authors,
    codename,
    config_path,
    date_hhmm,
    folder_path,
    name,
    region_dir,
    region_names,
    regions,
    version,
)
from tqdm.auto import tqdm

# Create study region folder if not exists
if not os.path.exists(f'{folder_path}/process/data/_study_region_outputs'):
    os.makedirs(f'{folder_path}/process/data/_study_region_outputs')
if not os.path.exists(region_dir):
    os.makedirs(region_dir)

# Compare and/or Copy parameters to study region directory if not already
# exists. This records a log of the assumptions under which an analysis was
# carried out and should also record if changes to parameters have occurred
# while a region has been analysed or re-analysed.  If the latter has
# occurred this could be problematic for reproducibility as it makes
# provenance of results unclear.
with open(f'{config_path}/config.yml') as f:
    project_configuration = yaml.safe_load(f)

current_parameters = {
    'date': date_hhmm,
    'project': project_configuration,
    codename: regions[codename],
}

if os.path.isfile(f'{region_dir}/_parameters.yml'):
    with open(f'{region_dir}/_parameters.yml') as f:
        saved_parameters = yaml.safe_load(f)
    if (
        current_parameters['project'] == saved_parameters['project']
        and current_parameters[codename] == saved_parameters[codename]
    ):
        print(
            f"The saved copy of region and project parameters from a previous analysis dated {saved_parameters['date'].replace('_',' at ')} at {region_dir}/_parameters_{saved_parameters['date']}.yml matches the current configuration parameters and will be retained.\n\n",
        )
    else:
        shutil.copyfile(
            f'{region_dir}/_parameters.yml',
            f'{region_dir}/_parameters_{saved_parameters["date"]}.yml',
        )
        with open(f'{region_dir}/_parameters.yml', 'w') as f:
            yaml.safe_dump(
                current_parameters,
                f,
                default_style=None,
                default_flow_style=False,
                sort_keys=False,
                width=float('inf'),
            )
        print(
            f"Project or region parameters from a previous analysis dated {saved_parameters['date'].replace('_',' at ')} appear to have been modified. The previous parameter record file has been copied to {region_dir}/_parameters_{saved_parameters['date']}.yml, while the current ones have been saved as {region_dir}/_parameters.yml.\n\n",
        )
else:
    with open(f'{region_dir}/_parameters.yml', 'w') as f:
        yaml.safe_dump(
            current_parameters,
            f,
            default_style=None,
            default_flow_style=False,
            sort_keys=False,
            width=float('inf'),
        )
    print(
        f'A dated copy of project and region parameters has been saved as {region_dir}/_parameters.yml.\n\n',
    )

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
pbar = tqdm(
    study_region_setup,
    position=0,
    leave=True,
    bar_format='{desc} ({n_fmt}/{total_fmt})\n{percentage:3.0f}%|{bar:70}|',
)
append_to_log_file = open(
    f'{region_dir}/__{name}__{codename}_processing_log.txt', 'a',
)
try:
    for step in pbar:
        pbar.set_description(study_region_setup[step])
        process = subprocess.check_call(
            f'python {step} {codename}',
            shell=True,
            cwd='./subprocesses',
            stderr=append_to_log_file,
            stdout=append_to_log_file,
        )
except Exception as e:
    print(
        f'\n\nProcessing {step} failed: {e}\n\n Please review the processing log file for this study region for more information on what caused this error and how to resolve it. The file __{name}__{codename}_processing_log.txt is located in the output directory and may be opened for viewing in a text editor.',
    )
finally:
    print(
        '\n\nOnce the setup of study region resources has been successfully completed, we encourage you to inspect the region-specific resources located in the output directory (e.g. text log file, geopackage output, csv files, PDF report and image files).',
    )
