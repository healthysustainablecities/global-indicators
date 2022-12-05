# Creating spatial urban indicators using the Global Healthy and Sustainable Cities Indicators Collaboration spatial urban indicators framework

The Global Healthy and Sustainable Cities Indicators Collaboration (GHSCIC) spatial urban indicators framework is designed to be run from a command line prompt, and once the software environment has been retrieved and running with the project configured, analysis for a particular city is undertaken in three steps:

1. Study region set up
2. Neighbourhood analysis
3. Aggregation

As a result of running the process, a geopackage of spatial features  for a specified and configured urban region is generated, including indicators for point locations, a small area grid (eg 100m), and overall city estimates.  In addition CSV files containing indicators for small area grid cells and the overall city are also generated, omitting geometry.

## Software installation and set up

Running the software requires installation of [Git](https://git-scm.com/) (to retrieve the software) and [Docker](https://www.docker.com/) (to set up the required computational environment and software dependencies).  The software is currently run from a command prompt, and on Windows systems we recommend the use of Windows Subsystem for Linux (wsl2) with this installed before installation of Docker, as this improves system performance (see instructions on [Docker Desktop WSL 2](https://docs.docker.com/desktop/windows/wsl/)).

Once Git is installed, the software may be retrieved by cloning this repository: 

```
git clone https://github.com/global-healthy-liveable-cities/global-indicators.git`
```

Once cloned, you can run `git pull` to ensure you have the latest version of the software as required.

Once Docker is installed and running, it can be used to retrieve or update and then launch containers for the spatial database (PostgreSQL with PostGIS and pgRouting) and the Global Indicators software environment, by running: 

```
bash ./global-indicators.sh
```

This runs a shell script containing a series of commands, which may be alternatively entered manually:

```
docker pull pgrouting/pgrouting
docker run --name=postgis -d -e POSTGRES_PASSWORD=ghscic -p 5433:5432 --restart=unless-stopped --volume=/var/lib/postgis:/postgresql/13/main pgrouting/pgrouting
docker pull globalhealthyliveablecities/global-indicators:latest
docker run --rm -it --shm-size=2g --net=host -v "$PWD":/home/jovyan/work globalhealthyliveablecities/global-indicators /bin/bash
```

This will launch the software in the root directory of the project, with the spatial database running as persistent storage in the background.  Change directory to the `process` folder to run the processing scripts:

```
cd process
```

## Configuration and data sourcing

Before commencing analysis, your project and study regions will need to be configured.  Configuration files which may be modified can first be initialised by running:

```python 00_create_project_configuration_files.py```

The following configuration files will then be located in the `process/configuration` folder, and may be be edited in a text editor (or in a spreadsheet editor such as Excel for the CSV file) to add and customise analysis for new regions:

- config.yml (overall project configuration)
- datasets.yml (defines datasets and metadata for OpenStreetMap and population, which can be referenced by regions)
- regions.yml (region specific details, including which datasets used - eg cities from a particular region could share common excerpts of population and OpenStreetMap, potentially)
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

## Analysis

1.  ```python 01_study_region_setup.py [CITY CODE NAME]```
    - This creates a database for the city and processes the resources required for analyses, as defined in `configuration/config.yml` (project parameters), `configuration/regions.yml` (region parameters), `configuration/osm_destination_definitions.csv` (OpenStreetMap destination definitions), and `configuration/osm_open_space.yml` (OpenStreetMap open space definitions).
        - To view the code names for configured cities, you can run the script without a city name: `python 01_study_region_setup.py`.  This displays the list of names for currently configured cities, each of which can be entered as arguments when running this script (city names are lower case, with underscores instead of spaces).
2.  ```python 02_neighbourhood_analysis.py [CITY CODE NAME]```
    - This script, run in the same way as for study region setup, performs local neighbourhood analysis for sample points across a city, creating urban indicators as defined in `indicators.yml`
3.  ```python 03_aggregation.py```
    - This script aggregates spatial urban indicator summaries for a small area grid (corresponding to the resolution of the input population grid) and overall city, exported as CSV (without geometry) and as layers to the geopackage file in the `data/study_region/[study region name]` folder.

The time taken to run analyses will vary depending on city size and density of features, and the specification of the computer running analyses.  A minimum of 8GB of RAM is recommended; in general, the more RAM and processors available, the better.  It is possible that lower specification machines will be able to perform analyses of smaller urban regions.   
