# Process study region resources for Global Indicators project

for i
do
    python 00_create_database.py $i
    python 01_create_study_region.py $i
    python 02_create_osm_resources.py $i
    python 03_create_network_resources.py $i
    python 04_create_hex_grid.py $i
    python 05_create_population_grid.py $i
    python 06_compile_destinations.py $i
    python 07_open_space_areas_setup.py $i
    python 08_locate_origins_destinations.py $i
    python 09_hex_destination_summary.py $i
    python 10_destination_audit.py $i
    python 11_urban_covariates.py $i
    python _export_gpkg.py $i
done
