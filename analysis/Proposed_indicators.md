# Global Indicator Project - proposed indicator discussion

Our methodology is to use globally open spatial data (especially OSM) first and foremost, and write process modules and python scripts to generate indicator calculation results. Then validate/supplement/substitute local (mostly open government) data if available and needed.  In analysing our results, we will need to comment (or even better, systematically benchmark) on a city-by-city basis the extent to which coverage/completeness of the data may have influenced the results for that city. 

Questions remain: 
** Define study region: residential vs. non-residental; urban vs. rural.  
** [Population Grids and Hexbin approaches](https://3.basecamp.com/3662734/buckets/11779922/messages/1857993142)  
** [Sample point selection](https://3.basecamp.com/3662734/buckets/11779922/messages/1770544113)
** [Frequent public transport definition](https://3.basecamp.com/3662734/buckets/11779922/messages/1825449219)
** Open space [source](https://3.basecamp.com/3662734/buckets/11779922/messages/1797801069) and [definition](https://3.basecamp.com/3662734/buckets/11779922/messages/1857459723)


## 1. Walkability (z-scores for local neigborhood dwelling density, street connectivity and daily living score) 

### street connectivity (calculated via OSMnx load stats, clean intersection density)
- cleaned intersection density for each local walkable neighborhood (the number of cleaned intersections of pedestrain network/total local walkable area)

### dwelling density 
- gross density: total number of dwellings within the cities/total area
- net density: use population raster (eg worldpop, or other) to derive a scaled-population density measure to serve as a proxy measure for dwelling density (e.g. take sum of population cells intersecting sausage buffer and divide by some indicative number for population per dwelling (e.g. 4) then standardise that result by dividing by the area of the sausage buffer in Hectares 

### land use mix/daily living scores
- % of land use allocated to residential, retail, civic and institutional, entertainment, recreation, food-related (can we get the land use data?)
- access to POIs (e.g. convenience, supermarket, and public transport stop)
	- using the sausage buffer technique and binary measures =1 for at least one POI within the walkable neighborhood, =0 for no POI within the walkable neighborhood. Counting the percentage of resident address/sample points within 1km/15min walk of an POI.
	- using the [pandana approach](https://github.com/gboeing/urban-data-science/blob/59afcff905649c5f8d1f8256ec37f28496e0c740/20-Accessibility-Walkability/pandana-accessibility-demo-full.ipynb) for network accessibility and walkability analysis: calculate distance to the nearest pois for each sample point neighborhood. Calculate the accessibility score based on the presence of at least one pois within 1km/15min walk using OD analysis for distance to the closest. (Or evaluate access with a destination specific soft threshold. [this post](https://3.basecamp.com/3662734/buckets/11779922/messages/1813713976))


** local walkable neighborhood: a 1600m walkable network and 50m buffer around OSM pedestrain street  
** Buffering technique referring to Forsyth et al [here](https://ij-healthgeographics.biomedcentral.com/articles/10.1186/1476-072X-11-14). Mavoa et al 2018, see [here](https://www.jtlu.org/index.php/jtlu/article/view/1132)  


## 2. Transport
### Access to any public transport
- % of population within mode specific distance to any public transport
- % of population to any frequent public transport within mode specific distance (how to define frequent transport - serviced every ? minutes on a normal day)

### Road and pedestrian network ratio
- Full road network (km) to pedestrian network (km)

## 3. Employment
### Access to employment
- % of population within 30 mins of home by walking
- % of population within 30 mins of home by cycling
- % of population within 30 mins of home by public transport

### Employment ratio
- Employed persons to working population

### Commute Distance
- Median commute distance for area


## 4. Density
### Access to places
- % of population within 1.2km of activity centres
- % of population within 1.2km of public transport hubs
- % of population within 1.2km of urban fringe developments

- % of urban fringe population within 1.2km of activity centres and public transport hubs
- % of non-urban fringe population within 1.2km of activity centres and public transport hubs

## 5. Destinations


## 6. Open space
- % of land area allocated to open space
- % of population access to public open space