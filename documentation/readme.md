# Understanding the Github Repository: 
The Github Repository (henceforth the repo) is named global-indicators, and the master is managed by Geoff Boeing. This section will describe what is information can be found in each part of the repo in a summarized form. For more detailed instruction, please look within the repo itself. If you are unfamiliar with Github, we recommend that you read the Github Guides which can be found at: https://guides.github.com/.

### Initial Readme
The repo’s readme gives an overview of the project’s goals and how the data was collected. Then, the workflow for calculating indicators is laid out. 
1.	First, import the city’s street network, pedestrian network, open space configuration, and destinations. In this section, sample points are created along every 30 meters of the pedestrian. These sample points will serve as the basis for the next section’s analysis.
1.	Create local walkable neighborhoods (henceforth neighborhoods) within each city for analysis. Neighborhoods are created by 
    1.  First, take a 1600 meter radius from each sample point
    1.  Second, buffer the edges within this 1600 meter radius by 50 meters
1.	Calculate different statistics for each neighborhood within the study region. This includes average population and intersection density. It also includes access to destinations and public open space. Finally, a walkability score is calculated from these statistics. 
1.	Convert data to the hex-level. 
    1.  Within-city: Average the statistics from step three into the hexagon level
    1.  Relative to all cities: Use z-sores to translate walkscore of hexes so that it can be understood relative to all cities 
1.	Finally, adjust for population. This allows to understand the indicators in terms of what the average person in the city experiences. This section also creates two indicators that represent the overall city-level walkability summaries, which are intended to show how walkable a city and its areas are for its population on average, compared with all other cities.
The end of the readme explains what to download and how to start contributing to the project.

## Different Documents
There are various documents that are accessible from the main repo. These include
-	.gitignore: A list of files for the repo to ignore. This keeps irrelevant files away from the main folders of the repo
-	LICENSE: Legal information concerning the repo and its contents
-   Win-docker-bash.bat: A file to smooth out the process of running Docker on a windows device 

## Docker Folder
The docker folder lets gives you the relevant information to pull the docker image onto your machine and run bash in this container. 
- On Windows open a command prompt and run:
  -	Type docker run --rm -it -v "%cd%":/home/jovyan/work gboeing/global-indicators /bin/bash
- On Mac/Linux open a terminal window and run:
  -	Type docker run --rm -it -v "$PWD":/home/jovyan/work gboeing/global-indicators /bin/bash

## Process Folder 
The process folder runs through the process of loading in the data and calculating the indicators. The initial readme goes step-by-step on the code to run. The configuration folder has the specific configuration json file for each study city. The data folder is empty before any code is run. The process folder also has five python scripts (henceforth scripts) and four jupyter notebooks (henceforth notebooks). This section will explain what each script and notebook does. This serves as basic understanding of what exists in the Process folder. To understand what steps to follow to run the process, please read the Process Folder’s readme. 

### Python Scripts vs Jupyter Notebooks
At the moment, May 2020, please run the scripts to calculate the indicators. While the scripts and the notebooks perform more or less the same process, the notebooks are still under development. As time moves on, the notebooks should be better developed, so they will become the best source of analysis. First, this section will discuss the scripts, then the notebooks will still be described.

### Setup_aggr.py and Setup_sp.py
These are modules that do not need to be run. Instead they work in the background and set up the definitions needed to run the Sample Points script (sp.py) and Aggregation script (aggr.py). In essence, they work as packages for the main process running scripts. For information on the difference of Scripts and Modules, you can look [HERE](https://realpython.com/run-python-scripts/). 

### Setup_config.py
Run this script first. This script sets the configuration files for each city study region. The configuration files make it easier to organize and analyze the different study cities by providing file paths for the input and output of each city. This configuration of file paths allows you to simply write the city name and allow the code to pull in all the city-specific data itself. It also makes it simple to add new study cities if required by the project.

### Sp.py
Run this script second. After projecting the data into the applicable crs, this script calculates data for the sample points. 
1.	First, intersection and population density are calculated for each sample point’s local walkable neighborhood. The script works for either the multiprocessing or single thread methods. 
1.	It then creates the pandana network for each sample point.  
1.	Next, the proximity of a sample point to each destination type is calculated within a certain distance (x). The distance is converted to a binary 0 or 1. 0 meaning the destination is not within the predetermined distance x, and 1 meaning that the destination is within the preset distance x. 
1.	Finally, a z-score for the variables is calculated  
This script must be run for each sample city in order run the aggregation script.

### Aggr.py
Run this script third. This is the last script needed to be run. This script converts the data from sample points into hex data. This allows for within city analysis. It also concatenates each city so that the indicators are calculated for between city comparisons. The concatenation is why the sample points script must be run for every city before running this script. After running the script, a geopackage is created in the output folder. 

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

The validation folder is currently dedicated to Phase II validation.

### Initial Readme
The Validation Folder’s readme explains how to run the official datasets for both street networks (edges) and destinations (poi – point of interest). Both the edge folder and the poi folder contain a readme file, a python script, and several python notebooks. The readme explains the results of the validation work. The script is a generalized way to run a cities data. Each notebook contains the code and results for a specific city.

### Edge
Edge data validation was conducted for Belfast, Olomouc, and Hong Kong. The analysis shows that the OSM network is much more extensive than the official network in all three cities. This is to be expected, however, because the OSM network include pedestrian paths that are not normally part of official datasets. Furthermore, the datasets closely match each other. When the official datasets for all three cities are buffered by 10 meters, about 90% edges intersect with the OSM data.

There are some portions of the official dataset, however, that cover parts of the network that the OSM data leaves out. Generally, these missing portions of the network are found on private property, and are mostly useful for internal circulation of those properties. Finally, in one case in Hong Kong, the official dataset includes roads that are planned for construction in a new development. OSM data does not include these roads because they are yet to be constructed. 

### poi
POI data validation was conducted for Belfast, Olomouc, and Sao Paulo. Only markets and fresh food vendors were included in this analysis. The analysis for each city varies. For Belfast, there are many more food-related destinations in the official data than in the OSM data. In Olomouc, there is very little difference between official and OSM data. In Sao Paulo, there are many fewer food-related destinations in the official data than in the OSM data. The key takeaway of this finding is that the definitions of what counts for food-related destinations varies greatly between urban study regions. It is still unclear if the OSM data is comprehensive for markets and fresh food vendors.  

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
The set of indicators chosen for calculation include:
- A walkability index (within city, and between city versions)
- Percent of population with access to frequent* public transport within 500 meters (* where frequency data is available)
- Percent of population with access to public open space
Walkability is calculated as a composite score using local neighborhood measures of population density, street connectivity, and land use mix. We use a score for proximal access to daily living amenities (fresh food, convenience, and public transport) as proxy measure for land use mix, which would otherwise be a challenge to calculate on a global scale.

##### Study Regions- 
The analysis area for each city included in the Global Livability Indicators project was constructed using the inter- section of a city administrative boundary (supplied by collaborators via a Google Form survey or acquired by the researchers independently) and urban centers identified by the Global Human Settlements project.

The use of an independent, global data source for urban centers helps to ensure that the analysis focus on exposure for urban populations across all cities, and not for example for lower density rural settings on the urban fringe, which may otherwise fall within an administrative boundary.

A large buffer (10 kilometers) was created around each study region, which defined the broader area of analysis for access to amenities. Built environment data — the network of roads and paths accessible by the public, and a series of destinations — were acquired for each city within the respective buffered study region boundaries.

The use of a buffer such as this ensures that the population who may live on the edge of the identified 
urban study region can still have access to nearby amenities evaluated, even if located outside the identified urban bounds. Access will only be analyzed up to 500 meters network distance for the present set of indicators, however the broader buffer area allows us flexibility for expanding analysis in the future.

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
A network analysis library in python that allows us to calculate the accessibility of different destinations. It does this by taking nodes and attaching an amenity to each node. For every node in the network, it calculated how many amenities are in the node. This information informs on the landscape of accessibility across the entire network. 

## Data

Retrieve the data from the links found in the following google doc:
https://docs.google.com/document/d/1NnV3g8uj0OnOQFkFIR5IbT60HO2PiF3SLoZpUUTL3B0/edit?ts=5ecc5e75



