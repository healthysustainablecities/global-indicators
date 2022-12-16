"""
Study region setup.

A wrapper script for deriving a study region's feature and network data from OpenStreetMap and other data sources to support subsequent indicator analyses.
"""

import subprocess
import sys

import yaml
from tqdm import tqdm

# Load study region configuration
region_configuration = "/home/ghsci/work/process/configuration/regions.yml"
with open(region_configuration) as f:
    regions = list(yaml.safe_load(f).keys())[1:]

if len(sys.argv) >= 2:
    if sys.argv[1] in regions:
        region = sys.argv[1]
    else:
        sys.exit(
            f"\nThe provided argument doesn't seem to match a configured region.  Please check that the region has been defined in the file {region_configuration}\n"
        )
else:
    sys.exit(
        f"\nPlease provide the code name for a configured study region as an argument when running this script.  The currently configured options include:\n\n{' '.join(regions)}\n"
    )

study_region_setup = {
    "00_create_database.py": "Create database",
    "01_create_study_region.py": "Create study region",
    "02_create_osm_resources.py": "Create OpenStreetMap resources",
    "03_create_network_resources.py": "Create pedestrian network",
    "04_create_population_grid.py": "Align population distribution",
    "05_compile_destinations.py": "Compile destinations",
    "06_open_space_areas_setup.py": "Identify public open space",
    "07_locate_origins_destinations.py": "Analyse local neighbourhoods",
    "08_destination_summary.py": "Summarise spatial distribution",
    "09_urban_covariates.py": "Collate urban covariates",
    "10_gtfs_analysis.py": "Analyse GTFS Feeds",
    "_city_summary_tex_table.py": "Summarize city",
    "_export_gpkg.py": "Export geopackage",
}
pbar = tqdm(study_region_setup)
try:
    for step in pbar:
        pbar.set_description(study_region_setup[step])
        try:
            process = subprocess.Popen(
                f"python {step} {region}",
                shell=True,
                cwd="./pre_process",
                stdout=open("./pre_process/_01_create_study_region.log", "a"),
            )
        except Exception as e:
            raise (f"Processing {step} failed: {e}")
        finally:
            process.wait()
except Exception as e:
    raise Exception(f"An error occurred: {e}")
finally:
    print(
        "\n\nOnce the setup of study region resources has been successfully completed, we encourage you to inspect the region-specific resources (either from the spatial database, or using the geopackage export file).  You can generate a validation report by running the _create_preliminary_validation_report.py script in the pre_process folder for a given study region also, which contains maps and summaries and may be shared with other local collaborators for advice.\n\n"
    )
