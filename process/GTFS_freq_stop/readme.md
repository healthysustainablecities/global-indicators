# Public Transport frequent stop analysis - with GTFS data

This folder contains the workflow and process scripts used for calculating the frequent PT stops using GTFS data for global indicators project study regions (if available).

The subfolder `gtfs_input_data` should contain input GTFS data for each study region used for the analysis

## Method

The stop headway analysis approach is developed to generalise frequent stop analysis method for the project study regions. It is revised based on the method previously developed by the Healthy Liveable Cities group for Australian cities led by Jonathan Arundel (2017-2018) and Carl Higgs (2019).  

### What is a “stop”?
- For train, stop = station (not platform)   
- For tram and bus, stop = physical stop (stops on opposite sides of the road are considered separately)  
- For ferry, stop = platform/wharf  
- Coach stops are not included by design (but would be excluded based on frequency criteria in any case)  

### Which stop qualify on a daily basis?
- Operates during normal day time from 7am to 7pm  
- Has a maximum headway less than or equal to 20 or 30 minutes  
- Operates during usual weekday (Monday to Friday). (note: It is difficult for some cities to determine a “usual weekday” – some modes run different timetables on different weekdays, and timetable changes are introduced frequently.)  

### How to define a “usual weekday”?
- Select feeds from 2019 and aim for the same season or school term (e.g. Spring-Summer school term time) to ensure comparability and consistency as much as possible.   

- Select a usual or representative one week during the feeds period that should fully capture the provided PT services in a city. This temporal filtering approach is adopted from [Kujala et. al. (2018) A collection of public transport network data sets for 25 cities](https://www.nature.com/articles/sdata201889#Sec21). The goal is to obtain as 'usual' week as possible (exluding public holiday etc.), which should contain at least 0.9 (default) of the total maximum of trips.   


## Set up and run the analysis

### This analysis requires installation of UrbanAccess package:  
```
conda install -c udst urbanaccess  
```
For UrbanAccess installation instructions see: https://udst.github.io/urbanaccess/installation.html  


### Set up study region GTFS analysis parameters in `gtfs_config.py`:   
- Many cities and countries that publish GTFS data provide non-standard custom licenses. Therefore, you may need to customize and manual check input data format and frequency parameters, and consider details of how headway is operationalized for each study region.

### Run the analysis script:
```
python gtfs_headway_analysis.py
```

## Outputs  

'frequent_transit_headway_2020May_python.gpkg' containing stop point layer with headway information for each study region
