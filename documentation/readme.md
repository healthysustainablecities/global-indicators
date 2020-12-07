# Understanding the Github Repository:
The Github Repository (henceforth the repo) is named global-indicators, and the master branch is managed by Geoff Boeing. This section will describe what is information can be found in each part of the repo in a summarized form. For more detailed instruction on to run different parts of the code, please look within folders the code exists within. If you are unfamiliar with Github, we recommend that you read the Github Guides which can be found at: https://guides.github.com/.

There are three work folders, a documentation folder, and an internal folder in the repo. The process folder holds the code and results of the main analysis for this project. The validation folder holds the codes, results, and analysis for the validation of the project. The analysis folder for output indicator visualization and analysis.  The internal folder, Docker, helps set up the docker environment for the project. In this readme, you will find a summary of what occurs in aspect of the repo.

## Main Directory
### Readme
The repo's readme gives a brief overview of the project and the indicators that are collected for analysis.

### Misc Documents
There are various documents that are accessible from the main repo. These include
-	.gitignore: A list of files for the repo to ignore. This keeps irrelevant files away from the main folders of the repo
-	LICENSE: Legal information concerning the repo and its contents
-	Win-docker-bash, docker-bash, docker-jupyter: Files help set up and smooth out the process of running Docker.

### Docker Folder
The docker folder lets gives you the relevant information to pull the docker image onto your machine and run bash in this container.

### Documentation Folder
The documentation folder contains this readme. The purpose of the documentation folder is to help you understand what the project does and how it does it.

## Process Folder
The process folder runs through the process of loading in the data and calculating the indicators. The readme goes step-by-step on the code to run. The configuration folder has the specific configuration json file for each study city. The data folder is empty before any code is run. The process folder also has five python scripts (henceforth scripts). This section will explain what each script and notebook does. This serves as basic understanding of what exists in the Process folder. To understand what steps to follow to run the process, please read the Process Folder’s readme.

### Preprocess Folder
The preprocess folder runs through the process of preparing input datasets. Currently, it contains a configuration file (project_configuration.xlsx) for the study regions defines both the project- and region-specific parameters, and the series of pre-processing scripts. The pre-processing procedure creates the geopackage and graphml files that are required for the subsequent steps of analysis. It is being coordinated by Carl. Please read the pre_process folder for more detail.

### Collaborator_report folder
This folder contains scripts to create a PDF validation report that was distributed to collaborators for feedback. Then, preprocessing will be revised as required by the collaborators feedback in an iterative process to ensure that data corroborated with the expectations of local experts. This is part of the effort for Phase I validation.

### Configuration Folder
The configuration folder contain configuration files for each of the 24 analyzed cities. The configuration files make it easier to organize and analyze the different study cities by providing file paths for the input and output of each city. This configuration of file paths allows you to simply write the city name and allow the code to pull in all the city-specific data itself. For example, each city has a different geopackage that is labled with 'geopackagePath' in the configuration file. The process code is able to extract the correct geopackage by using the configuration file. In Adelaide's case, 'adelaide_au_2019_1600m_buffer.gpkg' will be called whenever the code retreives 'geopackagePath' for Adelaide. The configuration files allow the project to be more flexible by creating an easy way to add, delete, or alter study city data.

### Data Folder
On the repo, the data contains instructions to download the data for the process is located data in the folder. Once obtained, process data will be stored in this folder. Information on the data is below. 

### setup_aggr.py and setup_sp.py
These are modules that do not need to be run. Instead they work in the background and set up the definitions for different functions needed to run the Sample Points script (sp.py) and Aggregation script (aggr.py). In essence, they work as packages for the main process running scripts. For information on the difference of Scripts and Modules, you can look [HERE](https://realpython.com/run-python-scripts/).

### setup_config.py
Run this script first. This script sets the configuration files for each city study region. Before running this script, the configuration folder will be empty.

### sp.py
Run this script second. After projecting the data into the applicable crs, this script calculates data for the sample points.
1.	First, intersection and population density are calculated for each sample point’s local walkable neighborhood. The script works for either the multiprocessing or single thread methods.
1.	It then creates the pandana network for each sample point.  
1.	Next, the proximity of a sample point to each destination type is calculated within a certain distance (x). The distance is converted to a binary 0 or 1. 0 meaning the destination is not within the predetermined distance x, and 1 meaning that the destination is within the preset distance x. As of December 2020, x is equal to 1,000 meters. 
1.	Finally, a z-score for the variables is calculated  
This script must be run first for each sample city before running the aggregation script.

### aggr.py
Run this script third. This is the last script needed to be run. This script converts the data from sample points into hex data. This allows for within city analysis. It also concatenates each city so that the indicators are calculated for between city comparisons. This concatenation is what necessitates running the sample points script every city before running this script. After running the script, Two indicators' geopackages will be created in the data/output folder.

### process_regions.sh
This is a shell script wrapper to run all study regions at once to process sample point estimates (sp.py) in sequence, and can be run using ```bash process_region.sh``` followed by a list of region names.

## Validation Folder
The project’s validation phase aims to verify the accuracy of the indicators processed from the data used in the process folder i.e. the global human settlement layer and OSM data (henceforth global dataset). In order to do this, we have three phases of validation.

Phase I validation is a qualitative assessment on how the global dataset matches with reality. For this step, collaborators from each city review the global dataset’s determined study region boundaries, population density, open space networks, and destination types, names, and categories for accuracy. Phase I validation is getting completed on an ongoing basis, and it is being coordinated by Carl.

Phase II validation compares the global dataset with a second dataset. The second dataset (henceforth official dataset) has been collected by local partners, so it will be individual for each city. The official dataset reflects what exists in public records. At the moment, the project has official datasets for four cities: Belfast, Olomouc, Hong Kong, and Sao Paulo. These four cities serve as case studies for the rest of the project by comparing the street networks and destinations in their official datasets with the global dataset.

Phase III validation is a comparison of the indicators that are derived from the global dataset and the official datasets. It will be difficult to run the process folder for the official datasets because of their inconsistent formats, so it may never be possible to run Phase III validation measures.

The Validation Folder’s readme explains how to run the code held within the folder.

### Configuration Folder
The validation configuration folder serves a similar purpose to the configuration folder in the process folder. The configuration files exists for each city for which the project has official data. Within the folder, the json files can have no information for certain filepaths because cities can have only edge data, only destination data, or edge and destination data.

### Data Folder
On the repo, the data contains instructions to download the data for validation is located data in the folder. Once obtained, validation data will be stored in this folder. Information on the data is below. 

### Edge and Destination Folders
Both the edge folder and the destination folder start with a readme file explaining what indicators are calulated. After running the python script, each folder will populate with a csv file containing relevant indicators and a fig folder for the created figures.

### Edge
The edge folder compares the OSM derived street network with the official street network.

### Destination
The destination folder compares fresh food destinations between the OSM derived data and the official data. This includes supermarkets, grocers, and shops like bakeries. A hexagon-grid analysis script helps aid in destination validation. 

## Data
-	2020 OSM Data (from 13 August 2020)
-	GHS Urban Centre Database 2015, multitemporal and multidimensional attributes, R2019A  (GHS_STAT_UCDB2015MT_GLOBE_R2019A_V1_2 , version 1.2, last updated 7 April 2020)
-	GHS population grid (GHS-POP), derived from GPW4.1, multi-temporal (1975-1990-2000-2015), R2019A[GHS_POP_MT_GLOBE_R2019A].
	-	We use the 2015 time point, using a virtual raster table constructed of geotiffs with global coverage in WGS84 EPSG 4326,
-	GTFS data targeting 2019, with approximately 4 April to 6 May in the northern hemisphere, and 8 October to 5 December in the southern hemisphere.  Years and dates vary by individual feed, pending availability.  
	-	Broadly, these are intended to capture the school term before summer school holidays, to aim for some kind of temporal / seasonal consistency between cities, as weather could plausibly influence transport scheduling / usage behaviours.


## Key Terms
Indicators-  
Indicators will be produced based on network analysis of sample points in urban areas of cities, with two output scales: a 250 meter hexagonal grid (for plotting the within city spatial distribution of measures); and city level summary.
The set of indicators chosen for calculation include:
- A walkability index (within city, and between city versions)
- Percent of population with access to frequent* public transport within 500 meters (* where frequency data is available)
- Percent of population with access to public open space
Walkability is calculated as a composite score using local neighborhood measures of population density, street connectivity, and land use mix. We use a score for proximal access to daily living amenities (fresh food, convenience, and public transport) as proxy measure for land use mix, which would otherwise be a challenge to calculate on a global scale.

##### Indicators-  
Indicators will be produced based on network analysis of sample points in urban areas of cities, with two output scales: a 250 meter hexagonal grid (for plotting the within city spatial distribution of measures); and city level summary.
The set of indicators chosen for calculation include are included in the following chart
Population per square kilometre
- Street connectivity per square kilometre
- Access to supermarkets within 500 metres
- Access to convenience stores within 500 metres
- Access to a public transport stop (any mode) within 500 metres
- Access to public open space (e.g. parks) within 500 metres
- Access to a frequent public transport stop (any mode) within 500 metres
- Daily Living Score within 500 metres (within and across cities)
    - The Daily Living Score is a composite of the different land use indicators. We use a score for proximal access to daily living amenities (fresh food, convenience, and public transport) as proxy measure for land use mix, which would otherwise be a challenge to calculate on a global scale.
- Walkability scores (within and across cities)
    - Walkability is calculated as a composite score using local neighborhood measures of population density, street connectivity, and land use mix.

##### Study Regions-
The analysis area for each city included in the Global Livability Indicators project was constructed using the inter- section of a city administrative boundary (supplied by collaborators via a Google Form survey or acquired by the researchers independently) and urban centers identified by the Global Human Settlements project.

The use of an independent, global data source for urban centers helps to ensure that the analysis focus on exposure for urban populations across all cities, and not for example for lower density rural settings on the urban fringe, which may otherwise fall within an administrative boundary.

A large buffer (10 kilometers) was created around each study region, which defined the broader area of analysis for access to amenities. Built environment data — the network of roads and paths accessible by the public, and a series of destinations — were acquired for each city within the respective buffered study region boundaries.

The use of a buffer such as this recognizes that the population who may live on the edge of the identified urban study region can still have access to nearby amenities evaluated, even if located outside the identified urban bounds. Access will only be analyzed up to 500 meters network distance for the present set of indicators, however the broader buffer area allows us flexibility for expanding analysis in the future.

##### Destinations-
- Freshfood Retailers such as Supermarkets (commonly used in built environment analysis as a primary source of fresh food), Markets (which may be a major source of fresh food in some locations of some cities), Bakeries, and other specific locations selling fresh food.
- Convenience stores (where basic and non-essential items may be acquired)
- Public transport (which might include bus, tram/light rail, train/metro/rail, ferry, etc.)
- Public open space, including ‘green space’, ‘squares’, or other kind of public area for pedestrians

##### OSMNX-
Learn more about OSMNX by going through Geoff Boeing’s Github repository.
https://github.com/gboeing/osmnx

##### Pandana Network-
A network analysis library in python that calculates the accessibility of different destinations. It does this by taking nodes and attaching an amenity to each node. For every node in the network, it calculates how many amenities are in the node. This information informs on the landscape of accessibility across the entire network.
