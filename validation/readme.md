# Running Phase II Validation

As of January 2021, edge validation data exists for:
- Belfast
- Olomouc
- Hong Kong

Destination validation data exists for:
- Belfast
- Olomouc
- Sao Paulo

This data will allow for **Phase II validation**. In Phase II validation, the dataset sourced from OSM is compared to official data from each individual city.

The following serves as instuctions for how to replicate **Phase II validation** for both **edge** and **destination** data.

## 1. Fork the Repo
1. Fork repository to your own GitHub account  
1. Clone repository to your local machine  
1. Make sure that your local version is up to the with remote:
    - Change directory to the **global-indicators** folder on your machine  
    - Run in your command prompt / terminal window:  
```git pull upstream master```  

Refer to the [GitHub Guides](https://guides.github.com/) regarding setup of local repository.

## 2. Download and Organize the Data
1. Download the data from the cloudstor. You can find the links to this data [HERE](https://docs.google.com/document/d/1NnV3g8uj0OnOQFkFIR5IbT60HO2PiF3SLoZpUUTL3B0/edit?ts=5ecc5e75).
1. Place the 'data' folder in the validation directory.  

## 3. Run Docker
1.  In the command prompt / terminal window, change your directory to the **"global-indicators folder"**.
1. Type the following to pull updated docker image:
```Docker pull gboeing/global-indicators:latest```  
1.  Start running docker in your machine
    - On Windows:
```docker run --rm -it -v "%cd%":/home/jovyan/work globalhealthyliveablecities/global-indicators /bin/bash```  
    - On Mac/Linux:
```docker run --rm -it -v "$PWD":/home/jovyan/work globalhealthyliveablecities/global-indicators /bin/bash```  
1. Change directory to **"global-indicators/validation"**

## 4. Run the Python Scripts

### Run edge_validation script
1. Change directory to **"global-indicators/validation/edge"**  
1. In the command prompt / terminal window, type
```python edge_validation.py```  

### Run destination_validation script
1. Change directory to **"global-indicators/validation/destination"**
1. In the command prompt / terminal window, type
```python destination_validation.py```
```python hexagon_points.py```
