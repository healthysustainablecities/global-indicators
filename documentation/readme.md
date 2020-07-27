# Understanding the Github Repository: 
The Github Repository (henceforth the repo) is named global-indicators, and the master branch is managed by Geoff Boeing. This section will describe what is information can be found in each part of the repo in a summarized form. For more detailed instruction on to run different parts of the code, please look within folders the code exists within. If you are unfamiliar with Github, we recommend that you read the Github Guides which can be found at: https://guides.github.com/.

There are two work folders and a documentation folder in the repo. The process folder holds the code and results of the main analysis for this project. The validation folder holds the codes, results, and analysis for Phase II validation of the project. In this readme, you will find a summary of what occurs in aspect of the repo. 

## Main Directory
### Readme
The repo's readme gives a breif overview of the project and the indicators that are collected for analysis. 

### Misc Documents
There are various documents that are accessible from the main repo. These include
-	.gitignore: A list of files for the repo to ignore. This keeps irrelevant files away from the main folders of the repo
-	LICENSE: Legal information concerning the repo and its contents
-   Win-docker-bash.bat: A file to smooth out the process of running Docker on a windows device 

### Docker Folder
The docker folder lets gives you the relevant information to pull the docker image onto your machine and run bash in this container. 
- On Windows open a command prompt and run:
  -	docker run --rm -it -v "%cd%":/home/jovyan/work gboeing/global-indicators /bin/bash
- On Mac/Linux open a terminal window and run:
  -	docker run --rm -it -v "$PWD":/home/jovyan/work gboeing/global-indicators /bin/bash

### Documentation Folder
The documentation folder contains this readme. The purpose of the documentation folder is to help you understand what the project does and how it does it. 

## Process Folder 
The process folder runs through the process of loading in the data and calculating the indicators. The readme goes step-by-step on the code to run. The configuration folder has the specific configuration json file for each study city. The data folder is empty before any code is run. The process folder also has five python scripts (henceforth scripts) and four jupyter notebooks (henceforth notebooks). This section will explain what each script and notebook does. This serves as basic understanding of what exists in the Process folder. To understand what steps to follow to run the process, please read the Process Folder’s readme. 

### Configuration Folder
The configuration folder contain configuration json files for each of the 25 analyzed cities. The configuration files make it easier to organize and analyze the different study cities by providing file paths for the input and output of each city. This configuration of file paths allows you to simply write the city name and allow the code to pull in all the city-specific data itself. For example, each city has a different geopackage that is labled with 'geopackagePath' in the configuration file. The process code is able to extract the correct geopackage by using the configuration file. In Adelaide's case, 'adelaide_au_2019_1600m_buffer.gpkg' will be called whenever the code retreives 'geopackagePath' for Adelaide. The configuration files allow the project to be more flexible by creating an easy way to add, delete, or alter study city data.

### Data Folder
On the repo, the data folder is empty. You are able to download the data for the process and place the data in this folder. Instructions for obtaining the data are below. 

### Python Scripts vs Jupyter Notebooks
At the moment, May 2020, please run the scripts to calculate the indicators. While the scripts and the notebooks perform more or less the same process, the notebooks are still under development. As time moves on, the notebooks should be better developed, so they will become the best source of analysis. First, this section will discuss the scripts, then the notebooks will be described.

### Setup_aggr.py and Setup_sp.py
These are modules that do not need to be run. Instead they work in the background and set up the definitions for different functions needed to run the Sample Points script (sp.py) and Aggregation script (aggr.py). In essence, they work as packages for the main process running scripts. For information on the difference of Scripts and Modules, you can look [HERE](https://realpython.com/run-python-scripts/). 

### Setup_config.py
Run this script first. This script sets the configuration files for each city study region. Before running this script, the configuration folder will be empty.

### Sp.py
Run this script second. After projecting the data into the applicable crs, this script calculates data for the sample points. 
1.	First, intersection and population density are calculated for each sample point’s local walkable neighborhood. The script works for either the multiprocessing or single thread methods. 
1.	It then creates the pandana network for each sample point.  
1.	Next, the proximity of a sample point to each destination type is calculated within a certain distance (x). The distance is converted to a binary 0 or 1. 0 meaning the destination is not within the predetermined distance x, and 1 meaning that the destination is within the preset distance x. 
1.	Finally, a z-score for the variables is calculated  
This script must be run for each sample city in order run the aggregation script.

### Aggr.py
Run this script third. This is the last script needed to be run. This script converts the data from sample points into hex data. This allows for within city analysis. It also concatenates each city so that the indicators are calculated for between city comparisons. The concatenation is why the sample points script must be run for every city before running this script. After running the script, a geopackage is created in the data/output folder. 

### 0_setup_config.ipynb
Generates the configuration files for each specific city. It then creates the configuration file for all the cities together. 

### 1_setup_sp_nh_stats.ipynb
Generates the sample point level indicators. Run this for every city. First, intersection and population density is calculated for each sample point’s local walkable neighborhood. Then distance to different destinations is calculated. Using these statistics, a walkscore is calculated for each sample point. 

### 2_aggr_output_ind.ipynb
Generates indicators for within city and across city analysis. 

### 3_show_ind_visual.ipynb
Generates a choropleth map that visualizes walkscore for each of the 24 study cities. 

## Validation Folder
The project’s validation phase aims to verify the accuracy of the indicators processed from the data used in the process folder i.e. the global human settlement layer and OSM data (henceforth global dataset). In order to do this, we have three phases of validation. 

Phase I validation is a qualitative assessment on how the global dataset matches with reality. For this step, collaborators from each city review the global dataset’s determined study region boundaries, population density, open space networks, and destination types, names, and categories for accuracy. Phase I validation is getting completed on an ongoing basis, and it is being coordinated by Carl.

Phase II validation compares the global dataset with a second dataset. The second dataset (henceforth official dataset) has been collected by local partners, so it will be individual for each city. The official dataset reflects what exists in public records. At the moment, the project has official datasets for four cities: Belfast, Olomouc, Hong Kong, and Sao Paulo. These four cities serve as case studies for the rest of the project by comparing the street networks and destinations in their official datasets with the global dataset. 

Phase III validation is a comparison of the indicators that are derived from the global dataset and the official datasets. It will be difficult to run the process folder for the official datasets because of their inconsistent formats, so it may never be possible to run Phase III validation measures. 

As of Summer 2020, the validation folder is dedicated to Phase II validation.

### Initial Readme
The Validation Folder’s readme explains how to run the official datasets for both street networks (edges) and destinations.

### Configuration Folder
The validation configuration folder serves a simmilar purpose to the configuration folder in the process folder. The configureation files exsit for each city for which the project has official data. Note, some cities have only edge data, only destination data, or edge and destination data. 

### Data Folder
On the repo, the data folder is empty. You are able to download the data for validation and place the data in this folder. Instructions for obtaining the data are below. 

### Edge and Destination Folders
Both the edge folder and the destination folder start with a readme file and a python script. The readme file explains the results of the validation work. Run the python script to conduct Phase II validation. After running the python script, each folder will populate with a csv file containing relevant indicators and a fig folder for the created figures.

### Edge
The edge folder compares the OSM derived street network with the offical street network. 

### Destination
The destination folder compares fresh food destinations between the OSM derived data and the official data. This includes supermarkets, markets, and shops like bakeries. 

## Data
Retrieve the data from the links found in the following google doc:
https://docs.google.com/document/d/1NnV3g8uj0OnOQFkFIR5IbT60HO2PiF3SLoZpUUTL3B0/edit?ts=5ecc5e75

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

The use of a buffer such as this ensures that the population who may live on the edge of the identified urban study region can still have access to nearby amenities evaluated, even if located outside the identified urban bounds. Access will only be analyzed up to 500 meters network distance for the present set of indicators, however the broader buffer area allows us flexibility for expanding analysis in the future.

##### Destinations- 
- Supermarkets (commonly used in built environment analysis as a primary source of fresh food)
- Markets (which may be a major source of fresh food in some locations of some cities)
- Shops, in general (which may include bakeries, or other specific locations selling fresh food)
- Convenience stores (where basic and non-essential items may be acquired)
- Public transport (which might include bus, tram/light rail, train/metro/rail, ferry, etc)
- Public open space, including ‘green space’, ‘squares’, or other kind of public area for pedestrians

##### OSMNX-
Learn more about OSMNX by going through Geoff Boeing’s Github repository. 
https://github.com/gboeing/osmnx

##### Pandana Network- 
A network analysis library in python that calculates the accessibility of different destinations. It does this by taking nodes and attaching an amenity to each node. For every node in the network, it calculates how many amenities are in the node. This information informs on the landscape of accessibility across the entire network. 

# Workflow for calculating the indicators

## Prepare study region input data sources, and city-specific config file
To get started, we need to prepare input datasource in geopackage format for each study region, these include:    
| Input data | Geometry | Description | Open data source |
| --- | --- | --- | --- |
| aos_nodes_30m_line | point | Public open space pseudo entry points (points on boundary of park every 20m within 30m of road) | OpenStreetMap |
| clean_intersections_12m |	point |	Clean intersections (not required; counts are associated with pop_ghs_2015) | OpenStreetMap |
| dest_type	| NA (non-spatial) |	Summary of destinations and counts | OpenStreetMap |
| destinations |	point	| OSM destinations retrieved using specified definitions (only require: supermarkets, convenience,  pt_any --- use dest_name_full to determine, will need to combine convenience destinations) | OpenStreetMap |
| pop_ghs_2015	| polygon	| 250m hex grid, associated with area_sqkm (fixed), population estimate (2015), population per sq km, intersection count, intersections per sq km | Global Human Settlement ([GHSL](https://ghsl.jrc.ec.europa.eu/download.php?ds=pop) |
| urban_sample_points |	point |	Sample points in urban region (every 30m along pedestrian network) | OpenStreetMap |
| urban_study_region | polygon | Urban study region (intersection of city boundary and GHS 2015 urban centre layer) | [GHSL](https://ghsl.jrc.ec.europa.eu/download.php?ds=pop) |


And study region pedestrian network graph:  
**studyregion_country_yyyy_10000m_pedestrian_osm_yyyymmdd.graphml**         		
- A derived 'pedestrian' network based on the OSM excerpt for the buffered study region (a 10km buffer around study region administrative boundary), processed using OSMnx with a custom walk-cycle tag filter (eg. excludes freeways and private roads / paths). 	 	
- The first entry of yyyy indicates the year the network is targetting; the date entry of yyyymmdd represents the retrieval date from OpenStreetMap.		
- The graphml can be loaded using OSMnx, and other packages that read the graphml format (networkx, gephi, etc).  

Urban sample points are created every 30m along pedestrian network to use as original points (to destination) for spatial network analysis. We adopted this sampling approach as residential address locations are not available to us in most cases.    

Population estimation (pop_ghs_2015) is retrieved from Global Human Settlement website ([GHSL](https://ghsl.jrc.ec.europa.eu/download.php?ds=pop)), and re-aggregated to 250m hex grid.    

Urban study region or boundary is created based on the intersection of official city boundary and GHS urban center layer. This adjustment is to restrain study region within urban areas, in order to better justify the use of OSM resources.  

Daily living destinations typically contain supermarkets, convenience stores, public transportation, and public open spaces. Destination points are retrieved from OSM's Points of Interests database.   

Other input datasource including walkable street network and intersections are retrieved from OSM using OSMnx.

We rely on OpenStreetMap database to conduct essential spatial analysis, with the idea that once the process are developed, they can be upscaled to other cities. However, modifications will be required to be made to each study region implementation to work in a global context.    

Please see `process/configuration` folder for examples in terms of how to prepare the config file for each study region. And See scripts: [setup_config.py](https://github.com/shiqin-liu/global-indicators/blob/master/process/setup_config.py) for detailed project parameters, and this notebook [0_setup_config.ipynb](https://github.com/shiqin-liu/global-indicators/blob/master/process/0_setup_config.ipynb) in the process folder for details on how cities configuration json files are prepared.  


## Prepare neighborhood (defined by 1600m radius pedestrian network of each sample point) level stats
For each sample point, 50m buffer is created along the OSM pedestrian street network within 1600m walking distance radius of each sample point (correspond with 20min walk). Each network buffer could be considered as a "local walkable neighborhood".   

Next, we calculate average population and intersection density for each local walkable neighborhood within study region.  
Detailed steps are as follows:   
&nbsp;&nbsp;1. load 250m hex grid from input gpkg with population and intersection density data  
&nbsp;&nbsp;2. intersect local walkable neighborhood (1600m) with 250m hex grid  
&nbsp;&nbsp;3. then calculate population and intersection density within each local walkable neighborhood (1600m) by averaging the hex level pop and intersection density data; final result is urban sample point dataframe with osmid, pop density, and intersection density.   

Then, we calculate sample point accessibility to daily living destinations (supermarket, convenience, & public transport) and public open space, and sample point walkability score.    
Detailed steps as follow:    
&nbsp;&nbsp;1. using pandana package to calculate distance to access from sample points to destinations (daily living destinations, public open space)  
&nbsp;&nbsp;2. calculate accessibility score per sample point: transform accessibility distance to binary measure: 1 if access <= 500m, 0 otherwise  
&nbsp;&nbsp;3. calculate daily living score per sample point by summing the binary accessibility scores to all daily living destinations  
&nbsp;&nbsp;4. calculate walkability score per sample point: get z-scores for daily living accessibility, population density and intersection; sum these three z-scores to get the walkability score    

The sample point stats outputs are saved back to city's input gpkg. A new layer *samplePointsData* will be created in each city's input gpkg.   
See scripts: [sp.py](https://github.com/shiqin-liu/global-indicators/blob/update_documentation/process/sp.py) or this notebook [1_setup_sp_nh_stats.ipynb](https://github.com/shiqin-liu/global-indicators/blob/update_documentation/process/1_setup_sp_nh_stats.ipynb) in the process folder for details.  

## Generate within-city indicators at the 250m hex grid level  
We rely on sample points stats that generated for each city to calculate the within-city indicators for each study region. This process take sample point stats within each study region as input and aggregate them up to hex-level indicators.

First, we calculate within-city indicators at hex level by taking the average of sample point stats within each hexagon. These sample point stats include pop and intersection density, daily living score, walkability score, and accessibility scores to destinations (supermarket, convenience, public transport and public open space).   

Next, we calculate walkability indicators at hex level relative to all cities. We first take the z-scores (relative to all cities) of pop and intersection density, and daily living generated at the hex level. Then, we sum these three z-scores to get the walkability index relative to all cities.

These within-city indicators are saved to a output gpkg, named *global_indicators_hex_250m.gpkg*. Layers with hex-level indicators will be created for each study region.    
See scripts: [aggr.py](https://github.com/shiqin-liu/global-indicators/blob/update_documentation/process/aggr.py) or this notebook [2_aggr_output_ind.ipynb](https://github.com/shiqin-liu/global-indicators/blob/update_documentation/process/2_aggr_output_ind.ipynb) in the process folder for details.     

Output *global_indicators_hex_250m.gpkg*:  

|indicators | data type | description |
|---- | --- | --- |
| urban_sample_point_count | int | Count of urban sample points associated with each hexagon (judge using intersect); this must be positive.  Zero sample count hexagons are not of relevance for output |
| pct_access_500m_supermarkets | float | Percentage of sample points with pedestrian network access to supermarkets within (up to and including) 500 metres |
| pct_access_500m_convenience | float | Percentage of sample points with pedestrian network access to convenience within (up to and including) 500 metres |
| pct_access_500m_pt_any | float | Percentage of sample points with pedestrian network access to public transport within (up to and including) 500 metres |
| pct_access_500m_public_open_space | float | Percentage of sample points with pedestrian network access to public open space within (up to and including) 500 metres |
| local_nh_population_density | float | Average local neighbourhood population density |
| local_nh_intersection_density | float | Average local neighbourhood intersection density |
| local_daily_living | float | Average local neighbourhood daily living score |
| local_walkability | float | Average local neighbourhood walkability score |
| all_cities_z_nh_population_density | float | Z-score of local neighbourhood population density relative to all cities |
| all_cities_z_nh_intersection_density | float | Z-score of local neighbourhood intersection density relative to all cities |
| all_cities_z_daily_living | float | Z-score of daily living score relative to all cities |
| all_cities_walkability | float | Walkability index relative to all cities |


## Generate across-city indicators at the city level  
We calculate population-weighted city-level indicators relative to all cities. We rely on the hex-level indicators that generated for each city (in *global_indicators_hex_250m.gpkg*) and population estimates (in study region input gpkg.) to calculate city-level indicators for across-cities comparison. This process take hex-level indicators (i.e. accessibility, pop density, street connectivity, within and across-city daily living and walkability) and population estimates within each study region as input and aggregate them up to city-level indicators using population weight.   


Output *global_indicators_city.gpkg*:

|indicators | data type | description |
|---- | --- | --- |
| pop_pct_access_500m_supermarkets | float | Percentage of population with pedestrian network access to supermarkets within (up to and including) 500 metres|
| pop_pct_access_500m_convenience | float | Percentage of population with pedestrian network access to convenience within (up to and including) 500 metres |
| pop_pct_access_500m_pt_any | float | Percentage of population with pedestrian network access to public transport within (up to and including) 500 metres |
| pop_pct_access_500m_public_open_space | float | Percentage of population with pedestrian network access to public open space within (up to and including) 500 metres |
| pop_nh_pop_density | float | Average local neighbourhood population density |
| pop_nh_intersection_density | float | Average local neighbourhood intersection density |
| pop_daily_living | float | Average daily living score for population (within city) |
| pop_walkability | float | Average walkability index for population (within city) |
| all_cities_pop_z_daily_living | float | Average z-score of daily living score for population relative to all cities |
| all_cities_walkability | float | Average walkability index for population relative to all cities|

The pop_* indicators represent the average experience of population within each study region in terms of overall city-level accessibility, population density, street connectivity, daily living and walkability.

The all_cities_* indicators represent the overall city-level walkability summaries, which are intended to show how walkable a city and its areas are for its population on average, compared with all other cities.

The across-city indicators are saved to a output gpkg, *global_indicators_city.gpkg*. A layer with city-level indicators will be created for each study region.      
See scripts: [aggr.py](https://github.com/shiqin-liu/global-indicators/blob/update_documentation/process/aggr.py) or this notebook [2_aggr_output_ind.ipynb](https://github.com/shiqin-liu/global-indicators/blob/update_documentation/process/2_aggr_output_ind.ipynb) in the process folder for details.   

Also see this notebook [3_show_ind_visual.ipynb](https://github.com/shiqin-liu/global-indicators/blob/update_documentation/process/3_%20show_ind_visual.ipynb) for indicator output visualization examples.