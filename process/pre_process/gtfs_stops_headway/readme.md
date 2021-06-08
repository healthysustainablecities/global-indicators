# Public transport stops with regular daytime weekday service - with GTFS data

This folder contains the workflow and process scripts used for analyzing the public transport stops headway using GTFS data for the project study regions (if available).


## Method
This headway analysis approach is developed to generalise frequent stop analysis method for the project study regions. It is revised based on the method previously developed by the Healthy Liveable Cities group for Australian cities led by Arundel et al (2017; https://apo.org.au/node/113921) and Carl Higgs (2019).

1. Set up study region GTFS analysis parameters (gtfs_config.py)
2. Load GTFS data into an UrbanAccess transit data frame
3. stops will be loaded limited within study region buffered bounding box
4. Stop headway analysis using average departure time during usual weekday (Monday-Friday) daytime (7am-7pm) for all feeds (one city can have more than one feeds) and modes of transport

### What is a “public transport stop”?
- For train, stop = station (not platform)   
- For tram and bus, stop = physical stop (stops on opposite sides of the road are considered separately)  
- For ferry, stop = platform/wharf  
- Coach stops are not included by design (but would be excluded based on frequency criteria in any case)  
- The modes of public transport in the GTFS specification: tram, metro, rail, bus, ferry, cable tram, aerial lift, funicular, trolleybus and Monorail

### Which stop qualify as regular service on a daily basis?
- Operates during normal day time from 7am to 7pm  
- Operates during usual weekday (Monday to Friday) during the time period of interest for that city

### How to define a “usual weekday”?
- Select feeds from 2019 and aim for the same season or school term (e.g. Spring-Summer school term time) to ensure comparability and consistency as much as possible.  
    - 5 April to 5 June for Northern Hemisphere cities; 8 October to 5 December for those in the Southern Hemisphere).  
    - Noted that not all schedules neatly met this criteria depending on the availability of the feeds data.


## Set up and run the analysis

### Download GTFS data in **gtfs_input_data** folder under the main **data** folder in this repository
The folder **gtfs_input_data** should contain input GTFS data for each study region used for the analysis. Most GTFS data used in this analysis are obtain from [Open Mobility data](https://transitfeeds.com/) and some from public transport agencies.  

First, create a subfolder named **gtfs_country_jurisdiction** (e.g. gtfs_us_seattle) within **gtfs_input_data** folder. Download and save study region GTFS file as **gtfs_country_jurisdiction_agency_yyyymmdd.zip** (e.g. gtfs_au_sa_adelaidemetro_20191004.zip; yyyymmdd represents the start date of the GTFS feed), then unzip the file before running the analysis.

### Set up study region GTFS analysis parameters in `gtfs_config.py`:    
Check `gtfs_config.py` for the example.  
Note: Many cities and countries that publish GTFS data provide non-standard custom licenses. Therefore, you may need to customize and manual check input data format and frequency parameters, and consider details of how headway is operationalized for each study region.    


### Run the analysis script:
```
python gtfs_headway_analysis.py
```

#### Or run this notebook `GTFS_headway_analysis.ipynb` for an individual city analysis

## Outputs  

Outputs are saved to 'frequent_transit_headway_yyyymm_python.gpkg' containing stop points layer with headway information for each study region
