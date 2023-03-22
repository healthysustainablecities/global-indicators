# Sub-processes
The following scripts form a sequential analysis workflow that is orchestrated from the process file, 2_analyse_region.py:

- _00_create_database.py: Create database
- _01_create_study_region.py: Create study region
- _02_create_osm_resources.py: Create OpenStreetMap resources
- _03_create_network_resources.py: Create pedestrian network
- _04_create_population_grid.py: Align population distribution
- _05_compile_destinations.py: Compile destinations
- _06_open_space_areas_setup.py: Identify public open space
- _07_locate_origins_destinations.py: Analyse local neighbourhoods
- _08_destination_summary.py: Summarise spatial distribution
- _09_urban_covariates.py: Collate urban covariates
- _10_gtfs_analysis.py: Analyse GTFS Feeds
- _11_export_gpkg.py: Export geopackage
- _12_neighbourhood_analysis.py: Analyse neighbourhoods
- _13_aggregation.py: Aggregate region summary analyses

The scripts may also be run individually by passing a city codename, as undertaken with the process scripts.
