import subprocess
import sys
from tqdm import tqdm
import yaml

# Load study region configuration
region_configuration = '/home/jovyan/work/process/configuration/regions.yml'
with open(region_configuration) as f:
     regions = list(yaml.safe_load(f).keys())[1:]

if len(sys.argv) >= 2:
    if sys.argv[1] in regions:
        region = sys.argv[1]
    else:
        sys.exit(f"\nThe provided argument doesn't seem to match a configured region.  Please check that the region has been defined in the file {region_configuration}\n")
else:
    region = 'ghent'

study_region_setup = [
    '00_create_database.py',
    '01_create_study_region.py',
    '02_create_osm_resources.py',
    '03_create_network_resources.py',
    '04_create_hex_grid.py',
    '05_create_population_grid.py',
    '06_compile_destinations.py',
    '07_open_space_areas_setup.py',
    '08_locate_origins_destinations.py',
    '09_hex_destination_summary.py',
    '10_destination_audit.py',
    '11_urban_covariates.py',
    '12_all_cities_gtfs_analysis.py'
]
pbar = tqdm(study_region_setup)
for step in pbar:
    pbar.set_description(step)
    try:
        process = subprocess.Popen(
            f"python {step} {region}",
            shell=True, 
            cwd="./pre_process",
            stdout=open('./pre_process/_01_create_study_region.log', 'a'))
    except:
        print(f"Processing {step} failed:")
        raise
    finally:
        process.wait()
