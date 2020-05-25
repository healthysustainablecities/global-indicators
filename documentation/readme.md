# Understanding the Github Repository: 
The Github Repository (henceforth the repo) is named global-indicators, and the master is managed by Geoff Boeing. This section will describe what is information can be found in each part of the repo in a summarized form. For more detailed instruction, please look within the repo itself. If you are unfamiliar with Github, we recommend that you read the Github Guides which can be found at: https://guides.github.com/.

### Initial Readme
The repo’s readme gives an overview of the project’s goals and how the data was collected. Then, the workflow for calculating indicators is laid out. 
1)	First, import the city’s street network, pedestrian network, open space configuration, and destinations. In this section, sample points are created along every 30 meters of the pedestrian. These sample points will serve as the basis for the next section’s analysis.
2)	Create local walkable neighborhoods (henceforth neighborhoods) within each city for analysis. Neighborhoods are created by 
a.	First, take a 1600 meter radius from each sample point
b.	Second, buffer the edges within this 1600 meter radius by 50 meters
3)	Calculate different statistics for each neighborhood within the study region. This includes average population and intersection density. It also includes access to destinations and public open space. Finally, a walkability score is calculated from these statistics. 
4)	Convert data to the hex-level. 
a.	Within-city: Average the statistics from step three into the hexagon level
b.	Relative to all cities: Use z-sores to translate walkscore of hexes so that it can be understood relative to all cities 
5)	Finally adjust for population. This allows to understand the indicators in terms of what the average person in the city experiences. This section also creates two indicators that represent the overall city-level walkability summaries, which are intended to show how walkable a city and its areas are for its population on average, compared with all other cities.
The end of the readme explains what to download and how to start contributing to the project.

## Different Documents
There are various documents that are accessible from the main repo. These include
•	.gitignore: A list of files for the repo to ignore. This keeps irrelevant files away from the main folders of the repo
•	LICENSE: Legal information concerning the repo and its contents

## Docker Folder
The docker folder lets gives you the relevant information to pull the docker image onto your machine and run bash in this container. 
On Windows open a command prompt and run:
•	docker run --rm -it -v "%cd%":/home/jovyan/work gboeing/global-indicators /bin/bash
On Mac/Linux open a terminal window and run:
•	docker run --rm -it -v "$PWD":/home/jovyan/work gboeing/global-indicators /bin/bash

## Process Folder 
The process folder runs through the process of loading in the data and calculating the indicators. The initial readme goes step-by-step on the code to run. The configuration folder has the specific configuration json file for each study city. The data folder is empty before any code is run. The process folder also has five python scripts (henceforth scripts) and four jupyter notebooks (henceforth notebooks). This section will explain what each script and notebook does. The Process Folder’s readme instructs on how to run the python scripts in the folder. This serves as basic instructions on how to use the folder. 

### Python Scripts vs Jupyter Notebooks
At the moment, May 2020, please run the scripts to calculate the indicators. While the scripts and the notebooks perform more or less the same process, but the notebooks are still under development. As time moves on, the notebooks should be better developed, so they will become the best source of analysis. First, this section will discuss the scripts, then the notebooks will still be described.

### Setup_aggr.py and Setup_sp.py
These are modules that do not need to be run. Instead they work in the background and set up the definitions needed to run the Sample Points script (sp.py) and Aggregation script (aggr.py). In essence, they work as packages for the main process running scripts. For information on the difference of Scripts and Modules, you can look HERE. 

### Setup_config.py
Run this script first. This script sets the configuration files for each city study region. The configuration files make it easier to organize and analyze the different study cities. It also makes it simple to add new study cities if required by the project.

### Sp.py
Run this script second. After projecting the data into the applicable crs, this script calculates data for the sample points. 
•	First, intersection and population density is calculated for each sample point’s local walkable neighborhood. The script works for either the multiprocessing or single thread methods. 
•	It then creates the pandana network for each sample point.  
•	Next, the proximity of a sample point to each destination type is calculated within a certain distance (x). The distance is converted to a binary 0 or 1. 0 meaning the destination is not within the predetermined distance x, and 1 meaning that the destination is within the preset distance x. 
•	Finally, a z-score for the variables is calculated  
This script must be run for each sample city in order run the aggregation script.

### Aggr.py
Run this script third. This is the last script needed to be run. This script coverts the data from sample points into hex data. This allows for within city analysis. It also concatenates each city so that the indicators are calculated for between city comparisons. The concatenation is why the sample points script must be run for every city before running this script. 

### Instructions to Run Scripts
In order to run the scripts, follow these steps. 
1.	Make sure that you have forked the repo onto your own GitHub account and that the repository is cloned onto your machine. For help on this, please refer to the GitHub Guides. 
2.	Download the global data from the cloudstor data folder. You can find the password to this link HERE.
3.	Rename the folder to ‘input’ and place the folder of data in ‘global-indicators/process/data’. 
4.	Create a second folder (this will one will be empty initially), named ‘output’. This should also be placed in ‘global-indicators/process/data’.
5.	In the command prompt / terminal window, change your director to the global-indicators folder. Then type the following
a.	Docker pull gboeing/global-indicators:latest
6.	Start running docker in your machine, and change directory to ‘global-indicators/process’. 
7.	Run scripts using the following code
a.	python setup_config.py
b.	python sp.py [SPECIFIC CITY NAME].json true
i.	Use the file name that can be found under the process/configuration folder for each city. Example: For Adelaide, type ‘python sp.py Adelaide.json true’
ii.	Only type true if using multiprocessing. On machines with lower capacity, I recommend not including ‘true’ in the command.
iii.	Make sure to run this line of code for each city before running aggr.py script
c.	python aggr.py cities.json
Note that it will take several hours to even some days to run these scripts, depending on the size of the study city. 

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

## Data
Where to find the data:

Global Datasets:
https://cloudstor.aarnet.edu.au/plus/s/LFkZfDUw2JiJKNv

Official Data for Phase II Validation:
https://cloudstor.aarnet.edu.au/plus/s/yBoGDKCfCRj2i7f


