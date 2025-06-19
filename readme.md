# Global Healthy and Sustainable Cities Indicators (global-indicators)
## Summary
An open-source tool for measuring, monitoring and reporting on policy and spatial urban indicators for healthy, sustainable cities worldwide using open or custom data.  Designed to support participation in the [Global Observatory of Healthy and Sustainable Cities](https://healthysustainablecities.org)' [1000 city challenge](https://www.healthysustainablecities.org/1000cities), it can be run as code or as an app in your web browser.  View the full documentation of the Global Healthy and Sustainable City Indicators software at https://healthysustainablecities.github.io/software/.

This software can be configured to support comparisons within- and between-cities and across time, benchmarking, analysis and monitoring of local policies, tracking progress, and inform interventions towards achieving healthy, equitable and sustainable cities.  It also support generating resources including maps, figures and reports in multiple languages, so these can be made accessible for use by local communities and stakeholders as a source of evidence to advocate for change.

![image](https://github.com/healthysustainablecities/global-indicators/assets/12984626/6f7d9c8a-47b2-496f-983b-820f5e86d0b5)

## What exactly does this do?
As a result of running the process, a core set of spatial indicators for healthy and sustainable cities are calculated for point locations, a small area grid (e.g. 100m), and overall city estimates.  Optionally, indicators can also be calculated for custom areas, like administrative boundaries or specific neighbourhoods of interest. In addition CSV files containing indicators for area summaries and the overall city are also generated, omitting geometry.

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

The tool can also be used to summarise and visualise a policy audit conducted using the 1000 Cities challenge tool.

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

## How to set up and get started?
### Software installation and set up

1. Download and unzip the [latest GHSCI software release](https://github.com/healthysustainablecities/global-indicators/releases) to a desired project directory on your computer
2. Install and run [Docker Desktop](hhttps://docs.docker.com/desktop/) according to the guidelines for your operating system of choice
3. Run the GHSCI software by opening the project directory where you extracted the software using a command line interface (e.g.  [Terminal](https://aka.ms/terminal) on Windows, [Terminal](https://support.apple.com/en-au/guide/terminal/apd5265185d-f365-44cb-8b09-71a064a42125/mac) on MacOS, or [Bash](https://www.gnu.org/software/bash/) on Linux):
  - on Windows open the folder in Terminal or cmd.exe and enter `.\global-indicators.bat`
  - on MacOS/Linux in bash, enter `bash ./global-indicators.sh`
    - Linux users may need to prefix this with 'sudo' for elevated permissions when launching Docker containers (read more [here](https://docs.docker.com/engine/install/linux-postinstall))


This will retrieve the computational environment and launch the Global Healthy and Sustainable City Indicators (GHSCI) software, along with a PostGIS spatial database that is used for processing and data management.  Once launched, instructions will be displayed.

![image](https://github.com/healthysustainablecities/global-indicators/assets/12984626/5192ad35-9418-4527-8e55-0316dec5bc62)

The software can be used to configure study regions, conduct analysis and generate resources in four ways, depending on preference:

- To launch the app in your web browser, type `ghsci` and open the displayed URL in your web browser
- To use a Jupyter Notebook, type `lab`, open the displayed URL in your web browser and double click to select the example notebook `example.ipynb` from the left-hand side browser pane
- The basic shortcut commands `configure`, `analysis`, `generate` and `compare` can be run at the commandline in conjunction with a codename referring to your study region
- Optionally, the process can be run in Python, for example:

```
# load the GHSCI software library
import ghsci

# load the example configured region
r = ghsci.example()

# or set a codename for your city, and use it to initialise or load a new region.
# The ghsci.example() is a shortcut for the following, that you could use for your own new study region.
codename = 'example_ES_Las_Palmas_2023'
r = ghsci.Region(codename)

# Once that is completed, you can proceed with analysis
r.analysis()

# and generating resources
r.generate()

# if you've analysed and generated results for other study regions, you can summarise the overall differences
r.compare('another_previously_processed_codename')

# if for some reason you want to drop the database for your study region to start again:
r.drop()

# You will be asked if you really want to do this!  It requires entering "ghscic" to confirm
# This doesn't remove any generated files or folders - you'll have to remove those yourself, if you want to
```

## Overview
The Global Healthy and Sustainable Cities Indicators (GHSCI) tool can be run in a web browser or as Python code (e.g. in Jupyter Lab).  Once the software environment has been retrieved and running, analysis for a particular city proceeds in four steps:

1. Configure study regions
2. Perform region analysis
3. Generate resources
4. Compare results (e.g. impact of hypothetical scenarios and sensitivity analyses, benchmarking between cities or regions of interest, monitoring change across time)

A fully configured example study region is provided along with data for users to familiarise themselves with the workflow and the possibilities of the generated resources.  Our [website](https://healthysustainablecities.github.io) provides detailed directions on how to perform the four-step process, and how to access, run and modify the provided example Jupyter notebook to perform analyses for your own study regions.

### Running the provided example
From the launched software prompt, type `ghsci` to start the web app and click the displayed link to open a web browser at http://localhost:8080

The Global Healthy and Sustainable City Indicators app opens to a tab for selecting or creating a new study region.  The software comes with an example configuration for the city of Las Palmas de Gran Canaria, Spain, that we can see has been `Configured` but hasn't yet had `Analysis` perormed or resources `Generated`.   Once two configured regions have had their resources generated, they can be compared.  Additionally, the results of a completed [policy checklist](https://healthysustainablecities.github.io/indicators/#Policy-indicator-analysis) can be summarised and queried.

![image](https://github.com/healthysustainablecities/global-indicators/assets/12984626/530f53fa-5989-48bf-8904-031faccb2225)

To run the example, click to select 'example_ES_Las_Palmas_2023' in the table, head to the `Analysis` tab and click the button.  While analysis is being conducted, progress will be summarised in the terminal.  This may take a few minutes to complete:

![image](https://github.com/healthysustainablecities/global-indicators/assets/12984626/ab5d2e51-4f94-459b-8fa4-212b46720373)

Once completed, the study region summary will have the `Analysed` check box ticked and if you click to select the example in the table it will display the configured study region boundary on the map:

![image](https://github.com/healthysustainablecities/global-indicators/assets/12984626/0d65bfb4-dcb8-4b9f-833e-cda12893034e)

Click the study region to view a popup summary of the core set of indicators calculated (spatial distribution data will be generated shortly, and directions for producing an interactive map are provided in the example Jupyter notebook).

To generate the range of resources listed above, with the example city selected navigate to the `Generate` tab and click the `Generate resources` button.  A series of outputs generated will be reported in the terminal window:

![image](https://github.com/healthysustainablecities/global-indicators/assets/12984626/1ccca037-49c7-49fa-aa0b-a9ca9ecfa003)

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

![image](https://github.com/healthysustainablecities/global-indicators/assets/12984626/c95e1ab4-3d89-49a6-86cb-61718f83dde5)

### Exit the software
To exit the web application click the **exit** button in the top right-hand corner. At the end of a Jupyter session, in the menu click _File > Shut Down_. If you close a browser window with the Jupyter Lab or GHSCI app still running, the underlying server process running these may be interrupted by pressing `Control+C` at the command prompt.

To run the analysis for your study region visit our website for detailed instructions on how to configure [a new study region](https://healthysustainablecities.github.io/software/#Details) and what [input data is required](https://healthysustainablecities.github.io/software/#Data).

# Optional indicators using Google Earth Engine

The two optional indicators of availability and access to large public urban green space, and the global urban heat vulnerability index are generated through use of Google Earth Engine - a cloud-based, planetary-scale, geospatial analysis platform that enables users to visualize and analyze satellite images. For more information, visit the Earth Engine [website](https://earthengine.google.com/) or read through the [academic paper](https://doi.org/10.1016/j.rse.2017.06.031) published in 2017.

Earth Engine is free for noncommercial and research use as detailed [here](https://earthengine.google.com/noncommercial/). Please follow the steps detailed below to create your own Google Cloud project and setup Earth Engine:

## Google Cloud project and Earth Engine setup

The following steps below mirror the official process published by Google outlined [here](https://developers.google.com/earth-engine/guides/access)

### Step 1. Create a Google Cloud project

If you haven't already, create a [Google Cloud project](https://cloud.google.com/resource-manager/docs/creating-managing-projects). You can do so from the [projects page](https://console.cloud.google.com/project) of the Cloud Console or use the following [link](https://console.cloud.google.com/projectcreate).

It is important to take note of the unique Project ID that is generated at this stage as you will need it in later steps. Take care to not confuse Project ID and Project name.

### Step 2. Enable the Earth Engine API

To enable the Earth Engine API for your project, use the following [link](https://console.cloud.google.com/apis/library/earthengine.googleapis.com) to go to the Earth Engine API page. On the Earth Engine API page, ensure that you have selected your project, and click the blue ENABLE button. If successful, you should see a green tick appear on the right-hand side of this button with the text 'API Enabled'

### Step 3. Register the project for commercial or non-commerial use

Edit the following URL by replacing `project-id` at the very end of the URL with your unique Project ID generated in step 1: `https://code.earthengine.google.com/register?project=project-id`

For example, if my Project ID was `example-project-123` I would edit the URL to the following:
`https://code.earthengine.google.com/register?project=example-project-123`

Visit the URL and complete the registration flow. You will have to answer 5 questions concerning your organisation type, non-commercial eligibility, and explaining the kind of work that you intend to use Earth Engine for. If you are unsure on how to answer these questions, feel free to use the following examples which relate to the context of the GHSCI software:

Question 2. Check non-commercial eligibility
How would you describe your use of Earth Engine? `Decision-making`
What is the geographic scope of your study? `Global`

Question 4. Describe your work
Does your work with Earth Engine fall into any of these categories? `Adaption`
Will you use Earth Engine for any of the following? `'City/Urban/Regional planning' and 'Public health'`

Once you have completed the process, click the blue 'Register' button.

## How to generate the optional spatial urban indicators

Now that you have successfully created a Google Cloud Project, enabled the Earth Engine API, and registered your project, following the below steps to generate the optional spatial urban indicators in the GHSCI software workflow.

### Step 4. Launch the Earth Engine container

At this point in time, the new Earth Engine inclusive workflow uses a different container to the 'original' GHSCI software container. This just means you need to launch the Earth Engine container using `.\global-indicators-ee.bat` or `.\global-indicators-ee.sh` depending on your operating system.

### Step 5. Enter your Cloud Project ID

Right after launching the Earth Engine container in your terminal, you will be prompted to enter your Cloud Project ID. This is the same Project ID that you generated upon sign up in step 1 and used in registration in step 3.

### Step 6. Grant access to Google Auth Library and copy verification code

Next, a long URL will appear in your terminal. Click (or copy) to open the link in your internet browser and follow the sign-in prompts. These involve the following:

  - Choose an account to sign in with Google. Make sure to sign in using the same Google account you used to create your Google Cloud project in step 1.
  - It will explain that you're signing in to Google Auth Library. Click 'continue'.
  - It will then state that Google Auth Library wants access to your Google Account. Click 'continue'.
  - Now a page will load with the title 'Sign in to the gcloud CLI'. To copy the verification code, click the white 'Copy' button at the bottom of the page.

Now return back to your terminal and paste the verification code.

### Step 7. Automatic quota project association and assets folder creation

Your cloud project will automatically be associated with your overall Google Earth Engine quota limit, and an assets folder will be created if it doesn't already exist.

At the end of this process, you should see a the following print message: Authentication successful!

This entire Earth Engine authentication process only needs to be run once. Once you exit the container using `exit` and then re-launch the Earth Engine container at a future time, the verification code you generated with this process will be saved and res-used. A message saying 'Using existing Google Cloud credentials setup previously' will print in the terminal, and the GHSCI software will operate as normal.

If you wish to view or delete your saved credentials and sign in with another Google account or use a different Cloud Project ID, then firstly launch the Earth Engine container as usual using either `.\global-indicators-ee.bat` or `.\global-indicators-ee.sh`. Now, open a second independent terminal and use the following commands as you require:

  - To check if the credentials file exists:
    `docker exec -it ghsci-ee bash -c "ls -la ~/.config/gcloud/"`

  - To read the credentials file:
    `docker exec -it ghsci-ee bash -c "cat ~/.config/gcloud/application_default_credentials.json"`

  - To delete the credentials file:
    `docker exec -it ghsci-ee bash -c "rm -f ~/.config/gcloud/application_default_credentials.json"`

If you delete the credentials file, exit the Earth Engine container, and then re-launch it again at a future time, then the above authentication process will begin again from step 4.

### Configuration file

Lastly, ensure that the `gee` in your city configuration file is set to `true` to generate these indicators.

## Citations

The software was developed by the [Global Healthy and Sustainable City Indicators Collaboration](https://www.healthysustainablecities.org/about#team) team, an international partnership of researchers and practitioners, extending methods developed by the [Planning and Transport for Healthy Cities](https://cur.org.au/themes/planning-transport-healthy-cities/) at RMIT University and incorporating functionality from the [OSMnx](https://github.com/gboeing/osmnx) tool developed by Geoff Boeing.

The software may be cited as:

> Higgs C, Lowe M, Giles-Corti B, Boeing G, Delclòs-Alió X, Puig-Ribera A, Adlakha D, Liu S, Borello Vargas JC, Castillo-Riquelme M, Jafari A, Molina-García J, Heikinheimo V, Queralt A, Cerin E, Resendiz E, Singh D, Rodriguez S, Suel E, Domínguez-Mallafré M, Ye Y, Alderton A. Global Healthy and Sustainable City Indicators: Collaborative development of an open science toolkit for calculating and reporting on urban indicators internationally. Environment and Planning B: Urban Analytics and City Science.0(0): https://doi.org/10.1177/23998083241292102

The concept underlying the framework is described in:

> Liu S, Higgs C, Arundel J, Boeing G, Cerdera N, Moctezuma D, Cerin E, Adlakha D, Lowe M, Giles-Corti B (2022) A Generalized Framework for Measuring Pedestrian Accessibility around the World Using Open Data. Geographical Analysis. 54(3):559-582. https://doi.org/10.1111/gean.12290

The tool was designed to be used for a 25-city comparative analysis, published as:

> Boeing G, Higgs C, Liu S, Giles-Corti B, Sallis JF, Cerin E, et al. (2022) Using open data and open-source software to develop spatial indicators of urban design and transport features for achieving healthy and sustainable cities. The Lancet Global Health. 10(6):e907–18. https://doi.org/10.1016/S2214-109X(22)00072-9

The process of scaling up residential analysis of liveability and sustainability indicators for diverse urban contexts is the topic of Carl Higgs' PhD research and is described in:

> Higgs, C. et al. (2022) ‘Policy-Relevant Spatial Indicators of Urban Liveability And Sustainability: Scaling From Local to Global’, Urban Policy and Research, 40(4). Available at: https://doi.org/10.1080/08111146.2022.2076215.

## Acknowledgements

This software is an officially sponsored Docker Open Source Software Project (https://hub.docker.com/u/globalhealthyliveablecities). The [broader programme of work this software supports](https://www.healthysustainablecities.org/about) received the Planning Institute of Australia's 2023 national award for Excellence in Planning Research.

Our approach, while supporting the optional use of custom data, was founded with an [open science ethos](https://www.unesco.org/en/open-science) and promotes the usage of global open data produced by individuals, organisations and governments including OpenStreetMap Contributors ([OpenStreetMap](https://wiki.openstreetmap.org/)), the European Commission Joint Research Centre ([Global Human Settlements Layer](https://ghsl.jrc.ec.europa.eu/)), and open data portals in general.  We gratefully acknowledge the valuable contributions to transparency, equity and science open data initiatives such as these and the producers of open source software underlying our work bring to the world.

Open source software we have used and which is included in our software environment includes [Python](https://www.python.org/) (programming language), [Docker](https://www.docker.com/) (software containerisation), [Conda](https://anaconda.org/) (package management), [PostgreSQL](https://www.postgresql.org/) (database), [PostGIS](http://postgis.net/) (spatial database), [pgRouting](https://pgrouting.org/) (routing analysis), [GDAL/OGR](https://doi.org/10.5281/zenodo.5884351) (Geospatial Data Abstraction software Library), [OSMnx](https://doi.org/10.1016/j.compenvurbsys.2017.05.004) (OpenStreetMap retrieval and network analysis), [NetworkX](https://networkx.org/) (network analysis), [fpdf2](https://py-pdf.github.io/fpdf2/) (PDF reporting), [NiceGUI](https://doi.org/10.5281/zenodo.8083457) (graphical user interface), [Jupyter Lab](https://jupyter.org/) (scientific code notebooks), [Pandas](https://pandas.pydata.org/) (dataframes), [GeoPandas](https://geopandas.org/en/stable/) (spatial dataframes), [GeoAlchemy](https://github.com/geoalchemy/geoalchemy2) (spatial SQL management), [SQLAlchemy](https://www.sqlalchemy.org/) (SQL management), [Pandana](https://github.com/UDST/pandana) (network analysis using pandas), [Rasterio](https://rasterio.readthedocs.io/en/stable/) (raster analysis), [GTFS-Lite](https://github.com/wklumpen/gtfs-lite/tree/master) (GTFS parsing), [Git](https://git-scm.com/) (source code management), [GitHub](https://github.com/about) (development platform), [Leaflet](https://leafletjs.com/) and Fabio Crameri's [Scientific colour maps](https://doi.org/10.5281/zenodo.1243862).

## How to contribute

### If you've found an issue or want to request a new feature:

  - check the [issues](https://github.com/healthysustainablecities/global-indicators/issues) first
  - open an new issue in the [issue tracker](https://github.com/healthysustainablecities/global-indicators/issues) filling out all sections of the template, including a minimal working example or screenshots so others can independently and completely reproduce the problem

### If you want to contribute to a feature:

  - post your proposal on the [issue tracker](https://github.com/healthysustainablecities/global-indicators/issues)
  - fork the repo, make your change (adhering to existing coding, commenting, and docstring styles)
  - Create your feature branch: `git checkout -b my-new-feature`
  - Commit your changes: `git commit -am 'Add some feature'`
  - Push to the branch: `git push origin my-new-feature`
  - Submit a pull request.
