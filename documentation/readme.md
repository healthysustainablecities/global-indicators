# Understanding the global-indicators repository:

To use this software, see the guide in the [process](../process) folder, which contains directions and code used to undertake analyses to create spatial urban indicators for healthy and sustainable cities.

If you are unfamiliar with Github, we recommend that you read the [Github Guides](https://guides.github.com/).

In addition to the **process** and **documentation** directories (the latter containing the guide you are reading now),  are the following:
- **maps**: a directory that optionally can be used for saving maps featuring the generated spatial urban indicators
- **validation** contains the code for Phase II validation of the 25 cities project (see [Liu et al. 2022](https://doi.org/10.1111/gean.12290)).
- **analysis** contains additional analyses undertaken as part of the 25 cities project (see [Boeing et al. 2022](https://doi.org/10.1016/S2214-109X(22)00072-9 )), or your own.
- **docker** details the docker environment used for the project (but which may be retrieved from Docker Hub using the directions in the process folder)


## Main Directory
### Readme
The repo's readme gives a brief overview of the project and the indicators that are collected for analysis.

### Misc Documents
There are various documents that are accessible from the main repo. These include:
-	**.gitignore**: A list of files for the repo to ignore. This keeps irrelevant files away from the main folders of the repo
-	**LICENSE**: Legal information concerning the repo and its contents
- 	**docker-bash.sh** and **Win-docker-bash.bat**: shell scripts that can be run to pull the most recent code and run the global-indicators software using Docker, on Linux (including Windows Subsystem for Linux) or Windows respectively.

## Process Folder
The [process](../process) folder contains detailed directions to set up and perform the 3-step process to calculate spatial indicators of urban design and transport features for healthy and sustainable cities, with data outputs in both geopackage (for mapping) and CSV (without geometry fields, for non-spatial analysis) formats.

### Configuration Folder
Configuration files contained in this folder can be edited to customise the project, urban regions of interest, datasets used, and indicators analysed.  Additionally, they provide a record of the parameters used to perform analyses.

### Data Folder
Datasources defined in the region and datasets configuration files can be stored in this folder as inputs for analysis.  In addition, city-specific subfolders will be created in a 'study_region' folder, containing intermediary and final output files with the results of analysis.

### Collaborator_report folder
This folder contains code for creating a PDF validation report that was distributed to collaborators for feedback, used in an iterative validation process with local experts.  This folder is referenced in a script `_create_preliminary_validation_report.py` which may be run from the pre-process folder.  This folder may be ignored.

### Pre-process Folder
The pre-process folder contains code used for preliminary analysis of cities when collating resources for neighbourhood analysis.  However, this code does not need to be run directly, and this folder may be ignored.   Optionally the various stages of pre-processing can be run from this folder, including creating a preliminary validation report.

## Validation Folder
The project’s validation phase aims to verify the accuracy of the indicators processed from the data used in the process folder i.e. the global human settlement layer and OpenStreetMap.

We conducted preliminary and iterative validation with our local expert collaborators, to ensure urban study region boundaries used were appropriate, population distribution data were adequately representative, and that destination categories and public open space areas were accurately and appropriately identified for the local context.  This was also referred to as 'Phase I validation'.

In addition, quantitative validation analyses were also conducted for our 25 city study.

### **OSM Edge and Destination Validation:**
A comparison of the global dataset with a second dataset. The second dataset **(henceforth official dataset)** has been collected by local partners and it is individual for each city. The official dataset reflects what exists in public records.
At the moment, the project has official datasets for four cities:
- Belfast
- Olomouc
- Hong Kong
- Sao Paulo
These four cities serve as case studies for the rest of the project by comparing the street networks and destinations in their official datasets with the global dataset.

### **Virtual Ground Truthing Validation**
A check of the validity of the OSM derived destinations. Specifically, this process is executed to understand the prevalence of false positive OSM derived destinations. This is done by comparing relevant destination locations to what exists on three Google services and assigning atrue or false value for each:
- Google Maps View (tag of the location)
- Google Satellite View (building footprint)
- Google Street View (Ground image).


### **Results Validation:**
Phase III validation includes the team analyzing results of the process to look for irregularities. In the cases where the results do not match with reality, the process and data are reviewed to see if the irregularities are explicable and amendable.

### **Robustness Check:**
Finally, as a robustness check, there is a comparison of the indicators that are derived from the global dataset and the official datasets. It will be difficult to run the process folder for the official datasets because of their inconsistent formats, so it may never be possible to run Phase III validation measures.

The Validation Folder’s readme explains how to run the code held within the folder.

### Configuration Folder
The validation configuration folder serves a similar purpose to the configuration folder in the process folder. The configuration files exists for each city for which the project has official data. Note, some cities have only edge data, only destination data, or edge and destination data.

### Data Folder
On the repo, the data contains instructions to download the data for validation is located data in the folder. Once obtained, validation data will be stored in this folder. Information on the data is below.

### Edge and Destination Folders
Both the edge folder and the destination folder start with a readme file explaining what indicators are calulated. After running the python scripts, each folder will populate with a csv file containing relevant indicators and a fig folder for the created figures.

### Edge
The edge folder compares the OSM derived street network with the official street network.

### Destination
The destination folder compares fresh food destinations between the OSM derived data and the official data. This includes supermarkets, grocers, and shops like bakeries. A hexagon-grid analysis script helps aid in destination validation.

## Data
For our 25 city study, the following data sources were used:

-	2020 OSM Data (from 13 August 2020)
-	GHS Urban Centre Database 2015, multitemporal and multidimensional attributes, R2019A  (GHS_STAT_UCDB2015MT_GLOBE_R2019A_V1_2 , version 1.2, last updated 7 April 2020)
-	GHS population grid (GHS-POP), derived from GPW4.1, multi-temporal (1975-1990-2000-2015), R2019A[GHS_POP_MT_GLOBE_R2019A].
	-	We use the 2015 time point, using a virtual raster table constructed of geotiffs with global coverage in WGS84 EPSG 4326,
-	GTFS data targeting 2019, with approximately 4 April to 6 May in the northern hemisphere, and 8 October to 5 December in the southern hemisphere.  Years and dates vary by individual feed, pending availability.
	-	Broadly, these are intended to capture the school term before summer school holidays, to aim for some kind of temporal / seasonal consistency between cities, as weather could plausibly influence transport scheduling / usage behaviours.

## Key Terms
##### Indicators
Indicators will be produced based on network analysis of sample points in urban areas of cities, with two output scales: a 250 meter hexagonal grid (for plotting the within city spatial distribution of measures); and city level summary.
The set of indicators chosen for calculation include are included in the following chart
- Population per square kilometre
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

##### Study Regions
Where possible, the analysis area for each city included in the Global Healthy and Sustainable City Indicators Collaboration 25-city study was constructed using the intersection of a city administrative boundary (supplied by collaborators via a Google Form survey or acquired by the researchers independently) and urban centers identified by the Global Human Settlements Layer (GHSL) Urban Centres Database (UCDB).  The use of an independent, global data source for urban centers helps to ensure a comparable definition of 'urban' is used across all cities, and not for example for lower density rural settings on the urban fringe, which may otherwise fall within an administrative boundary.  For some cities, local collaborators recommended customisation of the study region, including: use of a custom-defined boundary, use of the GHSL urban centre directly, or use of the administrative boundary (where a city was not otherwise included in the GHSL UCDB).

Study regions were buffered by a configurable distance (e.g. 1600m) further than the analyses conducted to mitigate risk of bias for areas on the urban fringe (e.g. who may be able to access urban features outside the city boundary). Environmental data including the population distribution, pedestrian network, destinations and areas of public open space were acquired and/or derived for each city's buffered study region boundary.

##### Destinations
- Supermarkets (commonly used in built environment analysis as a primary source of fresh food)
- Markets (which may be a major source of fresh food in some locations of some cities)
- Shops, in general (which may include bakeries, or other specific locations selling fresh food)
- Convenience stores (where basic and non-essential items may be acquired)
- Public transport (which might include bus, tram/light rail, train/metro/rail, ferry, etc)
- Public open space, including ‘green space’, ‘squares’, or other kind of public area for pedestrians

##### OSMnx
OSMnx is a Python package to modeling and analyzing spatial networks and other data from OpenStreetMap. Its documentation is [available here](https://osmnx.readthedocs.io/).

##### Pandana Network
A network analysis library in python that calculates the accessibility of different destinations. It does this by taking nodes and attaching an amenity to each node. For every node in the network, it calculates how many amenities are in the node. This information informs on the landscape of accessibility across the entire network.
bility across the entire network.
