# Global Healthy and Sustainable Cities Indicators (global-indicators)

An open-source tool for calculating spatial indicators for healthy, sustainable cities worldwide using open or custom data.

This software supports measuring, monitoring and reporting on policy and spatial urban indicators for comparisons within- and between-cities and across time. The methodology and the open data approach developed in this research can be configured to work for cities and region in diverse contexts worldwide to support benchmarking, analysis and monitoring of local policies, track progress, and inform interventions towards achieving healthy, equitable and sustainable cities.

As a result of running the process, a core set of spatial indicators for healthy and sustainable cities are calculated for point locations, a small area grid (eg 100m), and overall city estimates.  Optionally, indicators can also be calculated for custom areas, like administrative boundaries or specific neighbourhoods of interest. In addition CSV files containing indicators for area summaries and the overall city are also generated, omitting geometry.

The default core set of spatial urban indicators calculated includes:

- Urban area in square kilometers
- Population density (persons per square kilometre)
- Street connectivity (intersections per square kilometer)
- Access to destinations within 500 meters:
    - a supermarket
    - a convenience store
    - a public transport stop (any; or optionally, regularly serviced)
    - a public open space (e.g. park or square; any, or larger than 1.5 hectares)
- A score for access to a range of daily living amenities
- A walkability index

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

The resulting city-specific resources can be used to provide evidence to support policy makers and planners to target interventions within cities, compare performance across cities, and when measured across time can be used to monitor progress for achieving urban design goals for reducing inequities. Moreover, they provide a rich source of data for those advocating for disadvantaged and vulnerable community populations, to provide evidence for whether urban policies for where they live are serving their needs.

# How to set up and get started?

The Global Healthy and Sustainable Cities Indicators (GHSCI) tool can be run in a web browser or as Python code (e.g. in Jupyter Lab).  Once the software environment has been retrieved and running, analysis for a particular city proceeds in four steps:

1. Configure study regions
2. Perform region analysis
3. Generate resources
4. Compare results (e.g. impact of hypothetical scenarios and sensitivity analyses, benchmarking between cities or regions of interest, monitoring change across time)

Detailed directions to set up and perform the 3-step process to configure, conduct analysis and generate documented data, maps and reports on spatial indicators of urban design and transport features for healthy and sustainable cities are found on our website https://global-healthy-liveable-cities.github.io.

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
3. The basic shortcut commands `configure`, `analysis`, `generate` and `compare` can be run at the commandline in conjunction with a codename referring to your study region
4. Optionally, the process can be run in Python, for example:

```
from subprocesses import ghsci
# set a codename for your city; here is the codename for the provided example
codename = 'example_ES_Las_Palmas_2023'
# Initialise configuration file for your region
r = ghsci.Region(codename)
# Now, you need to source and download data, documenting metadata and file paths in the configuration file generated in the process/configuration/regions directory
# Once that is completed, you can proceed:
r.analysis()
r.generate()
# if you've analysed and generated results for other study regions, you can compare the main results
r.compare('another_previously_processed_codename')
# if for some reason you want to drop the database for your study region to start again:
r.drop()
# You will be asked if you really want to do this!  It requires entering "ghscic" to confirm
# This doesn't remove any generated files or folders - you'll have to remove those yourself, if you want to
```

Find out more about each of these ways of using the tool on our website.

## Running the provided example
From the launched software prompt, type `ghsci` to start the web app and click the displayed link open a web browser at http://localhost:8000

The Global Healthy and Sustainable City Indicators app opens to a tab for selecting or creating a new study region.  The software comes with an example configuration for the city of Las Palmas de Gran Canaria, Spain, that we can see has been `Configured` but hasn't yet had `Analysis` perormed or resources `Generated`.   Once two configured regions have had their resources generated, they can be compared.  Additionally, the results of a completed [policy checklist](https://global-healthy-liveable-cities.github.io/2023/02/01/indicators/#Policy-indicator-analysis) can be summarised and queried.

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

![image](https://github.com/global-healthy-liveable-cities/global-indicators/assets/12984626/c95e1ab4-3d89-49a6-86cb-61718f83dde5)

# Citations

Liu S, Higgs C, Arundel J, Boeing G, Cerdera N, Moctezuma D, Cerin E, Adlakha D, Lowe M, Giles-Corti B (2022) A Generalized Framework for Measuring Pedestrian Accessibility around the World Using Open Data. Geographical Analysis. 54(3):559-582. https://doi.org/10.1111/gean.12290

The tool was designed to be used for a 25-city comparative analysis, published as:

Boeing G, Higgs C, Liu S, Giles-Corti B, Sallis JF, Cerin E, et al. (2022) Using open data and open-source software to develop spatial indicators of urban design and transport features for achieving healthy and sustainable cities. The Lancet Global Health. 10(6):e907–18. https://doi.org/10.1016/S2214-109X(22)00072-9

# How to contribute

#### If you've found an issue or want to request a new feature:

  - check the [issues](https://github.com/global-healthy-liveable-cities/global-indicators/issues) first
  - open an new issue in the [issue tracker](https://github.com/global-healthy-liveable-cities/global-indicators/issues) filling out all sections of the template, including a minimal working example or screenshots so others can independently and completely reproduce the problem

#### If you want to contribute to a feature:

  - post your proposal on the [issue tracker](https://github.com/global-healthy-liveable-cities/global-indicators/issues)
  - fork the repo, make your change (adhering to existing coding, commenting, and docstring styles)
  - Create your feature branch: `git checkout -b my-new-feature`
  - Commit your changes: `git commit -am 'Add some feature'`
  - Push to the branch: `git push origin my-new-feature`
  - Submit a pull request.
