# Global liveability indicators project

## Background
RMIT University, in collaboration with researchers from other universities worldwide, is undertaking a project, the Global Indicators Project, to calculate health-related spatial built environment indicators for 25 cities globally; The project aims to make use of open data sources, such as OpenStreetMap, the Global Human Settlement Layer, and GTFS feeds (where available) as input to the indicator processing. After indicators have been derived for a city, members of the team who have local knowledge of that city will validate these.  

This (proposed) repository contains documentation and processes used in the global liveability indicators ('Lancet series') project, 2019.  

The processes are developed to create indicators for our selected global cities (with the potential that these processes could be applied to other cities). The indicators are:   
1. Population per square kilometre  
2. Street connectivity per square kilometre  
3. Access to supermarkets within 500 metres  
4. Access to convenience stores within 500 metres  
5. Access to a public transport stop (any mode) within 500 metres  
6. Access to public open space (e.g. parks) within 500 metres  
7. Access to a frequent public transport stop (any mode) within 500 metres  
8. Daily living score within 500 metres  
9. Walkability scores (within and across cities)

# Workflow for calculating study region indicators

## Prepare study region input data sources, and city-specific config file
To get started, we need to prepare input datasource in geopackage for your study region, these include:    
| Input data | Geometry | Description |
| --- | --- | --- |
| aos_nodes_30m_line | point | Public open space pseudo entry points (points on boundary of park every 20m within 30m of road) |
| clean_intersections_12m |	point |	Clean intersections (not required; counts are associated with pop_ghs_2015) |
| dest_type	| NA (non-spatial) |	Summary of destinations and counts |
| destinations |	point	| OSM destinations retrieved using specified definitions (only require: supermarkets, convenience,  pt_any --- use dest_name_full to determine, will need to combine convenience destinations) |
| pop_ghs_2015	| polygon	| 250m hex grid, associated with area_sqkm (fixed), population estimate (2015), population per sq km, intersection count, intersections per sq km |
| urban_sample_points |	point |	Sample points in urban region (every 30m along pedestrian network) |
| urban_study_region | polygon | Urban study region (intersection of city boundary and GHS 2015 urban centre layer) |

and study region network graph:  
*studyregion_country_yyyy_10000m_pedestrian_osm_yyyymmdd.graphml*		
	A derived 'pedestrian' network based on the OSM excerpt for the buffered study region ( a 10km buffer around study region administrative boundary), processed using OSMnx with a custom walk-cycle tag filter (eg. excludes freeways and private roads / paths). 		
	The first entry of yyyy indicates the year the network is targetting; the date entry of yyyymmdd represents the retrieval date from OpenStreetMap.		
	Can load up using OSMnx, and other packages that read the graphml format (networkx, gephi, etc).

Urban sample points are created every 30m along pedestrian network to use as original points (to destination) for spatial network analysis. We adopted this sampling approach as residential address locations are not available in most cases.    

Population estimation (pop_ghs_2015) is retrieved from Global Human Settlement ([GHSL](https://ghsl.jrc.ec.europa.eu/download.php?ds=pop)) datasets, and re-aggregate to 250m hex grid.    

Urban study region or boundary is created based on the intersection of official city boundary and GHS urban center layer. This adjustment is to restrain study region within urban areas, in order to accommodate the use of OpenSteetMap resources.

Daily living destinations typically contain supermarkets, convenience stores, public transportation, and public open spaces. Destination points are retrieved OpenSteetMap's Points of Interests database.

Other input datasource including walkable street network and intersections are retrieved from OpenSteetMap using OSMnx.

We rely on OpenStreetMap database to conduct essential spatial analysis, with the idea that once the process are developed, they can be upscaled to other cities. However, modifications will be required to be made to each study region implementation to work in a global context.


## Prepare neighborhood (defined by 1600m radius of each sample point) level stats
For each sample point, 50m buffer is created along the OSM pedestrain street network for 1600m walking distance radius of each sample point (correspond with 20min walk). Each network buffer could be considered as a "local walkable neighborhood".   

Next, we calculate average population and intersection density for each local walkable neighborhood within study regions.
Detailed steps are as follows:
    1. load 250m hex grid from disk with population and network intersections density data
    2. intersect local walkable neighborhood (1600m) with 250m hex grid
    3. then calculate population and intersection density within each local walkable neighborhood (1600m) by averaging the hex level pop and intersection density; final result is urban sample point dataframe with osmid, pop density, and intersection density  

Calculate sample point accessibility to daily living destinations (supermarket, convenience, & public transport) and public open space, and walkability score.  
Detailed steps as follow:
    1. using pandana packadge to calculate distance to access from sample points to destinations (daily living destinations, public open space)
    2. calculate accessibility score per sample point: transform accessibility distance to binary measure: 1 if access <= 500m, 0 otherwise
    3. calculate daily living score per sample point by summing the accessibility scores to all daily living destinations
    4. calculate walkability score per sample point: get zscores for daily living accessibility, population density and intersection; sum these three zscores to represent walkability score

The sample point stats outputs are saved back to city's input geopackage. A new layer *samplePointsData* will be created.  
See scripts: `sp.py` or `1_test_sp_ipynb` in the process folder for details

## Generate within-city indicators at the hex grid level  
We rely on sample points stats that generated for each city to calculate within-city indicators for each study region. This process take sample point stats within each study region as input and aggregate up to hex-level indicators.

First, we calculate within-city indicators at hex level by taking the average of sample point stats within each hexagon. These sample point stats include pop and intersection density, daily living score, walkability score, and accessibility scores to each destination (supermarket, convenience, public transport and public open space).   

Next, we calculate walkability indicators at hex level relative to all cities. We take the zscores (relative to all cities) of pop and intersection density, and daily living generated at the hex level. Then, we sum these three zscores tp get the walkability scores

The within-city indicators outputs are saved to a output geopackage, *global_indicators_hex_250m.gpkg*. A layer with hex-level indicators will be created for each study region.    
See scripts: `aggr.py` or `2_test_aggr_ipynb` in the process folder for details  

Output *global_indicators_hex_250m.gpkg*:  

|indicators | data type | description |
|---- | --- | --- |
| urban_sample_point_count | int | Count of urban sample points associated with each hexagon (judge using intersect); this must be positive.  Zero sample count hexagons are not of relevance for output |
| pct_access_500m_supermarkets | float | Percentage of sample points with pedestrian network access to supermarkets within (up to and including) 500 metres |
| pct_access_500m_covenience | float | Percentage of sample points with pedestrian network access to convenience within (up to and including) 500 metres |
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


## Generate between-city indicator at the city level  
We calculate population-weighted city-level indicators relative to all cities. We rely on hexagon-level indicators that generated for each city (saved in *global_indicators_hex_250m.gpkg*) and population estimates (saved in study region input gpkg.) to calculate city-level indicators for between and across-cities comparison. This process take hex-level indicators (i.e. accessibility, density, daily living and within and across-city walkability) and population estimates within each study region as input and aggregate them up to city-level indicators using population weight.   

These pop_* indicators represent the average experience of population within each study region in terms of overall city-level accessibility, population density, street connectivity, daily living and walkability.

The all_cities_* indicators represent the overall city-level walkability summaries, which are intended to show how walkable a city and its areas are for its population on average, compared with other cities.

The across-city indicators outputs are saved to a output geopackage, *global_indicators_city.gpkg*. A layer with city-level indicators will be created for each study region.      
See scripts: `aggr.py` or `2_test_aggr_ipynb` in the process folder for details  

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
