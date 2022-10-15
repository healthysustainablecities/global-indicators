# Running the Process
Please follow the instructions below to run the process.

## Run the Python Scripts

### 1. Fork the Repo
- Make sure that you have forked the repo onto your own GitHub account and that the repository is cloned onto your machine.
- Additionally, to make sure that your branch is up to date run the following in your command prompt / terminal window
    1. Change directory to the **global-indicators** folder on your machine
    1. Type the following:
        ```
        git pull upstream main
      ```

### 2. Set up project and study region parameter configuration
The project and study region parameters that determine where data data is located and how analyses are to be run are defined external to the code using plain text configuration files in the `configuration` folder. Project parameters can be modified by using a text editor to edit `config.yml`, while city or region-specific parameters can be modified using `regions_yml`.  Optionally, users may further refine the classification OpenStreetMap destinations for use in analyses by modifying `osm_destination_definitions.csv`, noting that additional custom destinations can be defined in `regions.yml` (although we would encourage users to contribute these to OpenStreetMap if they are lacking there, in the first instance). The methods used to identify areas of public open space may be further modified by editing `osm_open_space.yml`. 

Make sure you have setup project (`config.yml`) and region (`regions.yml`) configuration files for your analysis before proceeding the analysis, specifying the file location for a series of required datasets.  It is recommended to store these in the folders as indicated in the example configuration.  The datasets include:
- an OpenStreetMap .osm file with coverage of the region (and time) of interest; this could be an historical planet file from https://planet.openstreetmap.org/pbf/, or a region-specific excerpt from https://download.geofabrik.de/
- [Global Human Settlements Layer](https://ghsl.jrc.ec.europa.eu/download.php) Urban Centres database and gridded population data (we used R2019a, however are in the process of updating to use R2022a)
- [GTFS feed data](https://database.mobilitydata.org/), where available

### 3. Run Docker
1.  In the command prompt / terminal window, change your directory to the **global-indicators** folder. Then type the following
    ```
    Docker pull globalhealthyliveablecities/global-indicators:latest
    ```
1. It is also required to set up spatial database container, based on PostgreSQL with PostGIS and pgRouting, for example,
    ```
    docker pull pgrouting/pgrouting
    ```
1. To run the postgis server container with persistent storage (replace the password for Postgis to correspond to your project configuration)
```
docker run --name=postgis -d -e POSTGRES_PASSWORD=ghscic -p 127.0.0.1:5433:5432 --restart=unless-stopped --volume=/var/lib/postgis:/postgresql/13/main pgrouting/pgroutingt
```

1.  Start running docker in your machine
    - On Windows:
        ```
        docker run --rm -it -v "%cd%":/home/jovyan/work globalhealthyliveablecities/global-indicators /bin/bash
        ```
    - On Mac/Linux:
        ```
        docker run --rm -it -v "$PWD":/home/jovyan/work globalhealthyliveablecities/global-indicators /bin/bash
        ```
1. Change directory to the `process` folder to run the processing scripts.

### 4. Run the Python Scripts
1.  Run scripts using the following code
    1.  ```python 01_study_region_setup.py [CITY CODE NAME]```
        - This creates a database for the city and processes the resources required for analyses, as defined in `configuration/config.yml` (project parameters), `configuration/regions.yml` (region parameters), `configuration/osm_destination_definitions.csv` (OpenStreetMap destination definitions), and `configuration/osm_open_space.yml` (OpenStreetMap open space definitions).
        - To view the code names for configured cities, you can run the script without a city name: `python 01_study_region_setup.py`.  This displays the list of names for currently configured cities, each of which can be entered as arguments when running this script (city names are lower case, with underscores instead of spaces).
    1.  ```02_neighbourhood_analysis.py [CITY CODE NAME]```
        - This script, run in the same way as for study region setup, performs local neighbourhood analysis for sample points across a city, creating urban indicators as defined in `setup_config.py`
    1.  ```python 03_aggregation.py```
        - This script will attempt to aggregate the city indicator neighbourhood analyses for configured cities created as a result of running the previous scripts.  It assumes that analyses have been successfully completed for the list of configured cities.
        - Indicator summaries for overall cities and the hexagon grid will be exported as CSV (without geometry) and Geopackage files (for mapping) to **global-indicators/process/data/output**, with the date of processing indicated in the file name.

Note that it may take several hours to run these scripts, depending on the size of the study city. Also, the process requires a machine with more than 8 GB of memory in order to successfully run the largest cities.

## Run the Jupyter Notebooks

1. Follow steps 1 and 2 from the instructions above
1. Run docker:
    - On Windows:
          ```
          docker run --rm -it --name global-indicators -p 8888:8888 -v "%cd%":/home/jovyan/work globalhealthyliveablecities/global-indicators
          ```
    - On Mac/Linux:
         ```
         docker run --rm -it --name global-indicators -p 8888:8888 -v "$PWD":/home/jovyan/work globalhealthyliveablecities/global-indicators
        ```
2. Open a web browser and visit http://localhost:8888
3. Run the Jupyter Notebooks

Note that it will take several hours to several days to run these scripts, depending on the size of the study city.
