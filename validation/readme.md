# Running Phase II Validation

As of January 2021, edge validation data exists for Belfast, Olomouc, and Hong Kong and destination validation data exists for Belfast, Olomouc, and Sao Paulo. 

This data will allow for Phase II validation. In Phase II validation, the dataset sourced from OSM is compared to official data from each individual city.

THe following serves as instuctions for how to replicate Phase II validation for both edge and destination data.

## 1. Fork the Repo
- Make sure that you have forked the repo onto your own GitHub account and that the repository is cloned onto your machine. For help on this, please refer to the [GitHub Guides](https://guides.github.com/). 
- Additionally, to make sure that your branch is up to date run the following in your command prompt / terminal window
    1. Change directory to the global-indicators folder on your machine
    1. Type the following
    	- git pull upstream master

## 2. Download and Organize the Data
1. Download the data from the cloudstor. You can find the links to this data [HERE](https://docs.google.com/document/d/1NnV3g8uj0OnOQFkFIR5IbT60HO2PiF3SLoZpUUTL3B0/edit?ts=5ecc5e75).
1. Place the 'data' folder in the validation directory.  

## 3. Run Docker
1.  In the command prompt / terminal window, change your directory to the global-indicators folder. Then type the following
    1.  Docker pull gboeing/global-indicators:latest
1.  Start running docker in your machine
    - On Windows:
        - docker run --rm -it -v "%cd%":/home/jovyan/work gboeing/global-indicators /bin/bash
    - On Mac/Linux:
        - docker run --rm -it -v "$PWD":/home/jovyan/work gboeing/global-indicators /bin/bash
1. Change directory to ‘global-indicators/validation’

## 4. Run the Python Scripts 

### Run edge_validation script
1. Change directory to ‘global-indicators/validation/edge’
1. In the command prompt / terminal window, type
	- python edge_validation.py

### Run destination_validation script
1. Change directory to ‘global-indicators/validation/destination'
1. In the command prompt / terminal window, type
	- python destination_validation.py
    - python hexagon_points.py