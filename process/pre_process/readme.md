## Pre-processing
First, a configuration file for the study regions defines both the project- and region-specific parameters. Then, a shell script wrapper runs the pre-processing scripts which derive each region’s spatial data such as the street networks, destinations, population data, and hexagon grids into relevant terms for the project. The shell script wrapper is run using "bash ./process_region.sh" followed by a list of region names. Region Names can be retrieved using “python list_locales.py”. The pre-processing procedure creates the geopackage and graphml files that are required for the subsequent steps of analysis. 
 
### Files
-	Project and Region Specific Parameters Config File: pre_process/_project_configuration.xlsx
-	Shell Script Wrapper: process_region.sh
-	Bash: "bash ./process_region.sh [city name] [city name] [city name] [...]" 
-	Region-Name Retrieving: “python _list_locales.py”. 
-	Pre-Processing Scripts (the following displays the code contained in the bash script process_region.sh, which iterates over a supplied list of study region name arguments to run the series of 11 pre-processing scripts, and an export script). The scripts return "./data/study_regions/[city]_[region]_[year]/". The scripts are as follow:
	-    python 00_create_database.py $i
	-    python 01_create_study_region.py $i
	-    python 02_create_osm_resources.py $i
	-    python 03_create_network_resources.py $i
	-    python 04_create_hex_grid.py $i
	-    python 05_create_population_grid.py $i
	-    python 06_compile_destinations.py $i
	-    python 07_open_space_areas_setup.py $i
	-    python 08_locate_origins_destinations.py $i
	-    python 09_hex_destination_summary.py $i
	-    python 10_osm_audit_pop.py $i
	-    python 11_urban_covariates.py $i
	-    python _export_gpkg.py $i