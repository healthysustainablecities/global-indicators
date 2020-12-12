# Running Validation
## Overview
**As of June 2020:**  
Edge validation data exists for:
- Belfast
- Olomouc
- Hong Kong 

Destination validation data exists for:
- Belfast
- Olomouc
- Sao Paulo

This data will allow for **Phase II validation**. In Phase II validation, the dataset sourced from OSM is compared to official data from each individual city.

The following serves as instuctions for how to replicate **Phase II validation** for both **edge** and **destination** data.

## Running validation - **steps:**

1. Clone repository to your local machine  
2. Download and organize the data
3. Run docker
4. Run python scripts:
- run **edge_validation.py**  
- run **destination_validation.py**


## 1. Clone repository to your machine
- Fork repository to your own GitHub account  
- Clone repository to your local machine  
- Make sure that your local version is up to the with remote:
    - Change directory to the **global-indicators** folder on your machine  
    - Run in your command prompt / terminal window:  
```git pull upstream master```  

Refer to the [GitHub Guides](https://guides.github.com/) regarding setup of local repository. 

## 2. Download and organize the data
- Download the data from the [cloudstor](https://docs.google.com/document/d/1NnV3g8uj0OnOQFkFIR5IbT60HO2PiF3SLoZpUUTL3B0/edit?ts=5ecc5e75).  
- Place the 'data' folder in the validation directory  

## 3. Run Docker
- Change your directory to the **global-indicators** folder  
- Type the following in the command prompt / terminal window to pull docker image:  
```Docker pull gboeing/global-indicators:latest```  
- Start running docker in your machine:  
    - On Windows:  
```docker run --rm -it -v "%cd%":/home/jovyan/work gboeing/global-indicators /bin/bash```  
    - On Mac/Linux:  
```docker run --rm -it -v "$PWD":/home/jovyan/work gboeing/global-indicators /bin/bash```  

## 4. Run the Python Scripts 
- Run **edge_validation** script:  
    - Change directory to **"global-indicators/validation/edge"**  
    - In the command prompt / terminal window, type:  
```python edge_validation.py```  

- Run **destination_validation** script:  
    - Change directory to **"global-indicators/validation/destination"**
    - In the command prompt / terminal window, type:  
```python destination_validation.py```