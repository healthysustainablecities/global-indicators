# Creating spatial urban indicators using the Global Healthy and Sustainable Cities Indicators Collaboration spatial urban indicators framework

The Global Healthy and Sustainable Cities Indicators Collaboration (GHSCIC) spatial urban indicators framework is designed to be run from a command line prompt, and once the software environment has been retrieved and running, analysis for a particular city proceeds in three steps:

1. Configuration
2. Region analysis
3. Generate resources

As a result of running the process, a geopackage of spatial features for a specified and configured urban region is generated, including indicators for point locations, a small area grid (eg 100m), and overall city estimates.  In addition CSV files containing indicators for small area grid cells and the overall city are also generated, omitting geometry.  Optionally, PDF 'scorecard' reports summarising policy and spatial indicator results may be generated for dissemination.

Detailed usage notes are provided on the Global Healthy and Sustainable City Indicators tool [website].

## Software installation and set up

1. Download and unzip the [latest software release](https://github.com/global-healthy-liveable-cities/global-indicators/releases)
2. Install and run [Docker Desktop](https://www.docker.com/) according to the guidelines for your operating system of choice
3. Run the software a command prompt at the project directory
  - on Windows in cmd.exe enter '.\global-indicators.bat'
  - on MacOS/Linux in bash, enter 'bash ./global-indicators.sh'

Those scripts get Docker to retrieve the computational environment and dependencies for running our software. It launches the *ghsci* container (ie. Global Healthy and Sustainable City Indicators, another way of referring to our software) with the command line open at a directory where you can run the three scripts for configuring, analysing and reporting on a neighbourhood or region.  It also launches a PostGIS spatial database container in the background too, which helps with the processing and data management in the background.

## 1. Configuration and data sourcing

Before commencing analysis, your project and study regions will need to be configured.

Regions are configured using .yml files located within the `configuration/regions` sub-folder. An example region configuration for Las Palmas de Gran Canaria (for which data supporting analysis is included) has been provided in the file `process/configuration/regions/example_ES_Las_Palmas_2023.yml`, and further additional example regions have been provided.  The name of the file, for example `example_ES_Las_Palmas_2023`, acts a codename for the city when used in processing and avoids issues with ambiguity when analysing multiple cities across different regions and time points: 'example' clarifies that this is an example, 'ES' clarifies that this is a Spanish city, 'Las_Palmas' is a common short way of writing the city's name, and the analysis is designed to target 2023 (i.e. it uses data sources published then). The .yml file is a text file used to define region specific details, including which datasets used - eg cities from a particular region could share common excerpts of population and OpenStreetMap, potentially).

Additional configuration files which may be modified can first be initialised by running:

```python 1_create_project_configuration_files.py```

The following configuration files will then be located in the `process/configuration` folder, and may be be edited in a text editor (or in a spreadsheet editor such as Excel for the CSV file) to add and customise analysis for new regions:

- config.yml (overall project configuration)
- datasets.yml (defines datasets and metadata for OpenStreetMap and population, which can be referenced by regions)
- indicators.yml (some aspects of indicators calculated can be modified here, although this isn't necessary; currently this is set up for our core indicators)
- osm_destinations.csv (a table of key pair tags that collectively identify the kinds of destinations to be evaluated for accessibility)
- osm_open_space.yml (definitions for identifying areas of open space using OpenStreetMap)

The datasets and regions configuration files are the main ones that will require customisation to process new regions.

The required datasets are:

- an OpenStreetMap .pbf file with coverage of the region (and time) of interest; this could be an historical planet file from https://planet.openstreetmap.org/pbf/, or a region-specific excerpt from https://download.geofabrik.de/
- [Global Human Settlements Layer](https://ghsl.jrc.ec.europa.eu/download.php) Urban Centres database and/or administrative boundary for urban region of interest
  - the GHSL urban centres database may be saved and extracted to a folder like `process/data/GHS/GHS_STAT_UCDB2015MT_GLOBE_R2019A`, with this path recorded in the `urban_region` section of `process/configuration/datasets.yml`.
  - Where possible and appropriate, we recommend using the intersection of an administrative boundary for a city's metropolitan area with the empirically identified 'urban area' from the GHSL data.  The location of a geopackage containing an administrative boundary for the urban region of interest may be recorded under the `area_data` field for that region in `process/configuration/regions.yml`.   For example, "`area_data: ./data/boundaries.gpkg:Ghent`" identifies the boundaries.gpkg geopackage as having a layer named 'Ghent' corresponding to the configured Ghent study region.
- Population distribution grid data with coverage of urban region of interest
  - [GHS population grid (R2022)] (https://ghsl.jrc.ec.europa.eu/download.php?ds=pop) is recommended (for example, the 2020 Molleweide 100m grid tiles corresponding to your area of interest, with these saved and extracted to a folder like  `process/data/GHS/R2022A/GHS_POP_P2030_GLOBE_R2022A_54009_100_V1_0`, which may be specified in `process/configuration/datasets.yml`.

Optionally, projects can be configured to:

- analyse [GTFS feed data](https://database.mobilitydata.org/) for evaluating accessibility to regularly serviced public transport
- use custom sets of OpenStreetMap tags for identifying destinations (see [OpenStreetMap TagInfo](https://taginfo.openstreetmap.org/) and region-specific tagging guidelines to inform relevant synonyms for points of interest)
- use custom destination data (a path to CSV with coordinates for points of interest for different destination categories can be configured in `process/configuration/regions.yml`)

## 2. Analysis

To analyse a configured region, enter

```python 2_analyse_region.py [CITY CODE NAME]```

This creates a database for the city and processes the resources required for analyses, as defined in `configuration/config.yml` (project parameters), `configuration/regions.yml` (region parameters), `configuration/osm_destination_definitions.csv` (OpenStreetMap destination definitions), and `configuration/osm_open_space.yml` (OpenStreetMap open space definitions).

To view the code names for configured cities, you can run the script without a city name.  This displays the list of names for currently configured cities, each of which can be entered as arguments when running this script (city names are lower case, with underscores instead of spaces).

Local neighbourhood analysis for sample points is then performed across a city, creating urban indicators as defined in `indicators.yml`.

Finally, spatial urban indicator summaries are aggregated for a small area grid (corresponding to the resolution of the input population grid) and overall city, exported as CSV (without geometry) and as layers to the geopackage file in the `data/study_region/[study region name]` folder.

## 3. Reporting

To generate reports for the results, run

```python 3_generate_resources.py [CITY CODE NAME]```

This script is used to generate reports, optionally in multiple languages, for processed cities.  It integrates the functionality previously located in the repository https://github.com/global-healthy-liveable-cities/global_scorecards, which was used to generate [city reports](https://doi.org/10.25439/rmt.c.6012649) for our 25 city study across 16 languages.  These can be configured using the configuration file _report_configuration.xlsx in conjunction with the regions, indicators and policies configuration files.

The time taken to run analyses will vary depending on city size and density of features, and the specification of the computer running analyses.  A minimum of 8GB of RAM is recommended; in general, the more RAM and processors available, the better.  It is possible that lower specification machines will be able to perform analyses of smaller urban regions.
