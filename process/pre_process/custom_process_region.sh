# Process study region resources for Global Indicators project

for i
do
    # python 00_create_database.py $i
    # python 01_create_study_region.py $i
    # python 02_create_osm_resources.py $i
    # python 03_create_network_resources.py $i
    # python 04_create_sample_points.py $i
    # python 05_create_hex_grid.py $i
    # python 06_create_population_grid.py $i
    # python 07_compile_destinations.py $i
    # python 08_open_space_areas_setup.py $i
    # python 09_locate_origins_destinations.py $i
    python 10_hex_destination_summary.py $i
    python 11_osm_audit_pop.py $i
    python _export_gpkg.py $i
done
