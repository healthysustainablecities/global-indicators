# Creating spatial urban indicators using the Global Healthy and Sustainable Cities Indicators Collaboration spatial urban indicators framework

The Global Healthy and Sustainable Cities Indicators Collaboration (GHSCIC) spatial urban indicators framework is designed to be run from a command line prompt, and once the software environment has been retrieved and running, analysis for a particular city proceeds in three steps:

1. Configure study regions
2. Perform region analysis
3. Generate resources

As a result of running the process, a core set of spatial indicators for healthy and sustainable cities are calculated for point locations, a small area grid (eg 100m), and overall city estimates.  Optionally, indicators can also be calculated for custom areas, like administrative boundaries. In addition CSV files containing indicators for small area grid cells and the overall city are also generated, omitting geometry.  

Generated outputs include:
  - Summary of configuration parameters used for analysis (.yml file)
  - Processing log detailing the analyses undertaken (.txt file)
  - Geopackage of indicator results and spatial features including points and areas of interest and pedestrian network (.gpkg)
  - CSV files for indicator results (.csv)
  - Data dictionaries (.csv and .xlsx files)
  - ISO19115 metadata (.xml and .yml files)
  - Analysis report (pdf)
  - Policy and spatial indicator report, optionally in multiple languages (.pdf)
  - Figures and maps, optionally in multiple languages (.jpg)

Detailed usage notes are provided on the Global Healthy and Sustainable City Indicators tool [website](https://global-healthy-liveable-cities.github.io/).

A fully configured example study region is provided along with data for users to familiarise themselves with the workflow and the possibilities of the generated resources.

## Software installation and set up

1. Download and unzip the [latest software release](https://github.com/global-healthy-liveable-cities/global-indicators/releases)
2. Install and run [Docker Desktop](https://www.docker.com/) according to the guidelines for your operating system of choice
3. Run the software a command prompt at the project directory
  - on Windows in cmd.exe enter '.\global-indicators.bat'
  - on MacOS/Linux in bash, enter 'bash ./global-indicators.sh'
    - Linux users may need to prefix this with 'sudo' for elevated permissions when launching Docker containers (read more [here](https://docs.docker.com/engine/install/linux-postinstall))

This will retrieve the computational environment and launch the Global Healthy and Sustainable City Indicators (GHSCI) software, along with a PostGIS spatial database that is used for processing and data management.  Once launched, instructions will be displayed.  

The software can be used to configure study regions, conduct analysis and generate resources in four ways, depending on preference:

1. To launch the app in your web browser, type `ghsci`
2. To use a Jupyter Notebook, type `lab` and open the example notebook `example.ipynb`
3. The basic commands `configure`, `analysis`, `generate` and `compare` can be run at the commandline in conjunction with a codename referring to your study region
4. Optionally, the modules can also be imported and used in Python scripts

Find out more about each of these ways of using the tool on our website.

## Running the provided example
From the launched software prompt, type `ghsci` to start the web app and click the displayed link to open a web browser at http://localhost:8080

The Global Healthy and Sustainable City Indicators app opens to a tab for selecting or creating a new study region.  The software comes with an example configuration for the city of Las Palmas de Gran Canaria, Spain, that we can see has been `Configured` but hasn't yet had `Analysis` perormed or resources `Generated`.   Once two configured regions have had their resources generated, they can be compared.  Additionally, the results of a completed [policy checklist](https://global-healthy-liveable-cities.github.io/indicators/#Policy-indicator-analysis) can be summarised and queried.

![image](https://github.com/global-healthy-liveable-cities/global-indicators/assets/12984626/530f53fa-5989-48bf-8904-031faccb2225)

To run the example, click to select 'example_ES_Las_Palmas_2023' in the table, head to the `Analysis` tab and click the button.  While analysis is being conducted, progress will be summarised in the terminal.  This may take a few minutes to complete:

![image](https://github.com/global-healthy-liveable-cities/global-indicators/assets/12984626/ab5d2e51-4f94-459b-8fa4-212b46720373)

Once completed, the study region summary will have the `Analysed` check box ticked and if you click to select the example in the table it will display the configured study region boundary on the map:

![image](https://github.com/global-healthy-liveable-cities/global-indicators/assets/12984626/0d65bfb4-dcb8-4b9f-833e-cda12893034e)

Click the study region to view a popup summary of the core set of indicators calculated (spatial distribution data will be generated shortly, and directions for producing an interactive map are provided in the example Jupyter notebook).

To generate the range of resources listed above, with the example city selected navigate to the `Generate` tab and click the `Generate resources` button.  A series of outputs generated will be reported in the terminal window:

![image](https://github.com/global-healthy-liveable-cities/global-indicators/assets/12984626/1ccca037-49c7-49fa-aa0b-a9ca9ecfa003)

You can use the `Compare` function to 
- evaluating the overall impact of parameters and data used (sensitivity analyses)
- compare results of different cities (benchmarking)
- compare results for the same study region across time (monitoring)
- evaluate the impact of hypothetical scenarios or interventions through analysis of modified data to represent these

As an example of a sensitivity analysis of the urban boundary used for analysis:
  - take a copy of the 'example_ES_Las_Palmas_2023.yml' file and save it as `ES_Las_Palmas_2023_test_not_urbanx`.  
  - Open this file in a text editor and 
    - modify the entry under study_region_boundary reading `ghsl_urban_intersection: true` to `ghsl_urban_intersection: false`
    - modify the value of the parameter entry for 'notes' (line 57) to read "This supplementary configuration file for the broader administrative boundary region of Las Palma allows the impact of restricting analysis to the urban region (as per the main example) to be evaluated."
  - now, exit the application (click the button in the top right hand corner) and restart the application
  - select the new region and perform the analysis and generate resources steps
  - select the `example_ES_Las_Palmas_2023` study region and navigate to the `Compare` tab
  - select the `ES_Las_Palmas_2023_test_not_urbanx` region from the comparison drop down menu and click `Compare study regions` to generate a comparison CSV in the example study region's output folder (`process\data\_study_region_outputs\example_ES_Las_Palmas_2023`) and display a table with sideby side comparison of the overall region statistics and indicator estimates in the app window:
  - 
![image](https://github.com/global-healthy-liveable-cities/global-indicators/assets/12984626/c95e1ab4-3d89-49a6-86cb-61718f83dde5)

## Additional information (see our [website](https://global-healthy-liveable-cities.github.io/) for details)
### Study region configuration
Before commencing analysis, your study regions will need to be configured with details of your downloaded data, the metadata used to document this data, and parameters to guide the software's usage of this data in analyses.

Regions are configured using .yml files located within the `configuration/regions` sub-folder. An example region configuration for Las Palmas de Gran Canaria (for which data supporting analysis is included) has been provided in the file `process/configuration/regions/example_ES_Las_Palmas_2023.yml`, and additional example regions have been provided in a sub-folder.  The name of these files, for example `example_ES_Las_Palmas_2023`, acts a codename for the city when used in processing and avoids issues with ambiguity when analysing multiple cities across different regions and time points: 'example' clarifies that this is an example, 'ES' clarifies that this is a Spanish city, 'Las_Palmas' is a common short way of writing the city's name, and the analysis is designed to target 2023 (i.e. it uses data sources published then). The .yml file is a text file used to define region specific details, including which datasets used - eg cities from a particular region could share common excerpts of population and OpenStreetMap, potentially).

To configure a new study region, you can copy the provided example to a new file and edit this.  Alternatively, if you use the `configure` process to create a new study region it will initialise the configuration file with descriptions for each of the parameters.

Additional configuration files will be initialised in the `process/configuration` folder, and may be be edited in a text editor (or in a spreadsheet editor such as Excel for the CSV file) to add and customise analysis for new regions, including

- `datasets.yml` to define datasets and metadata for OpenStreetMap, population, urban regions and transit feeds that can be shared and referenced by multiple study regions
- `config.yml` for overall project configuration

Optionally, projects can be configured to:

- analyse [GTFS feed data](https://database.mobilitydata.org/) for evaluating accessibility to regularly serviced public transport
- use custom sets of OpenStreetMap tags for identifying destinations (see [OpenStreetMap TagInfo](https://taginfo.openstreetmap.org/) and region-specific tagging guidelines to inform relevant synonyms for points of interest)
- use custom destination data (a path to CSV with coordinates for points of interest for different destination categories can be configured in `process/configuration/regions.yml`)


### Required data
- an OpenStreetMap .pbf file with coverage of the region (and time) of interest; this could be an historical planet file from https://planet.openstreetmap.org/pbf/, or a region-specific excerpt from https://download.geofabrik.de/
- [Global Human Settlements Layer](https://ghsl.jrc.ec.europa.eu/download.php) Urban Centres database and/or administrative boundary for urban region of interest
  - the GHSL urban centres database may be saved and extracted to a folder like `process/data/GHS/GHS_STAT_UCDB2015MT_GLOBE_R2019A`, with this path recorded in the `urban_region` section of `process/configuration/datasets.yml`.
  - Where possible and appropriate, we recommend using the intersection of an administrative boundary for a city's metropolitan area with the empirically identified 'urban area' from the GHSL data.  The location of a geopackage containing an administrative boundary for the urban region of interest may be recorded under the `area_data` field for that region in `process/configuration/regions.yml`.   For example, "`area_data: ./data/boundaries.gpkg:Ghent`" identifies the boundaries.gpkg geopackage as having a layer named 'Ghent' corresponding to the configured Ghent study region.
- Population distribution grid data with coverage of urban region of interest
  - [GHS population grid (R2023)] (https://ghsl.jrc.ec.europa.eu/download.php?ds=pop) is recommended (for example, the 2020 Molleweide 100m grid tiles corresponding to your area of interest, with these saved and extracted to a folder like  `process/data/GHS/R2023A/GHS_POP_E2020_GLOBE_R2023A_54009_100_V1_0`, which may be specified in `process/configuration/datasets.yml`.  *Take care to select the correct Epoch for your analysis before downloading!*

### System resources and processing time
The time taken to run analyses will vary depending on city size and density of features, and the specification of the computer running analyses.  A minimum of 8GB of RAM is recommended; in general, the more RAM and processors available, the better.  It is possible that lower specification machines will be able to perform analyses of smaller urban regions.  The provided example city of Las Palmas de Gran Canaria should take about 8 minutes to run on a standard laptop, however some larger cities may take a number of hours to process.
