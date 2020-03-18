# Global liveability indicators project

## Background
RMIT University, in collaboration with researchers from other universities worldwide, is undertaking a project, the Global Indicators Project, to calculate health-related spatial built environment indicators for 25 cities globally; The project aims to make use of open data sources, such as OpenStreetMap (OSM), the Global Human Settlement Layer (GHSL), and GTFS feeds (where available) as input to the indicator processing. After indicators have been derived for a city, members of the team and study region collaborators who have local knowledge of that city will validate these indicators.  

This (proposed) repository contains documentation and process scripts used for calculating the global liveability indicators in the ('Lancet series') project, 2019.  

The processes are developed to create indicators for our selected global cities (with the potential that these processes could be applied to other study region globally). These indicators are:   
1. Population per square kilometre  
2. Street connectivity per square kilometre  
3. Access to supermarkets within 500 metres  
4. Access to convenience stores within 500 metres  
5. Access to a public transport stop (any mode) within 500 metres  
6. Access to public open space (e.g. parks) within 500 metres  
7. Access to a frequent public transport stop (any mode) within 500 metres  
8. Daily living score within 500 metres (within and across cities)
9. Walkability scores (within and across cities)

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

Please see `process/configuration` folder for examples in terms of how to prepare the config file for each study region.  


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

# How to set up and get started?

* install [Git](https://git-scm.com/downloads) and [Docker](https://www.docker.com/products/docker-desktop)

* git clone https://github.com/gboeing/global-indicators.git, or fork the repo and then git clone a local copy to your machine

* for update run from the forked repository:
```
git pull upstream master
```

* set up analysis environment container

```
Run docker pull gboeing/global-indicators:latest
```

* Download the study region data files shared on [Cloudstor](https://cloudstor.aarnet.edu.au/plus/s/j1UababLcIw8vbM), and place them in the `/process/data/input` folder.

* Then, check `process` folder for more detail script running process
