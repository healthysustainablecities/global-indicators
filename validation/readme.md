# HOW TO RUN SCRIPTS NEEDS TO BE INCLUDED

# Running Validation

As of June 2020, edge validation data exists for Belfast, Olomouc, and Hong Kong and destination validation data exists for Belfast, Olomouc, and Sao Paulo. 

This data will allow for Phase II validation. In Phase II validation, the dataset sourced from OSM is compared to official data from each individual city.

THe following serves as instuctions for how to replicate Phase II validation for both edge and destination data.

## 1. Fork the Repo
- Make sure that you have forked the repo onto your own GitHub account and that the repository is cloned onto your machine. For help on this, please refer to the GitHub Guides. 
- Additionally, to make sure that your branch is up to date run the following in your command prompt / terminal window
    1. Change directory to the global-indicators folder on your machine
    1. Type git pull upstream master

## 2. Download and Organize the Data
1.  Download the data from the cloudstor. You can find the links to this data HERE.
1. Place the folder 'edge validation' in the 'edge' folder. Rename 'edge validation' folder to 'data'.  
1. Place the folder 'poi validation' in the 'destination' folder. Rename 'edge validation' folder to 'data'.  

## 3. Run Docker
1.  In the command prompt / terminal window, change your directory to the global-indicators folder. Then type the following
    1.  Type Docker pull gboeing/global-indicators:latest
1.  Start running docker in your machine
    - On Windows:
        - Type docker run --rm -it -v "%cd%":/home/jovyan/work gboeing/global-indicators /bin/bash
    - On Mac/Linux:
        - Type docker run --rm -it -v "$PWD":/home/jovyan/work gboeing/global-indicators /bin/bash
1. Change directory to to ‘global-indicators/validation’

## 4. Run the Python Scripts 

### Run edge_validation script
1. 
### Run destination_validation script
1. 