# Global Indicator Project - proposed indicator discussion

## 1. Walkability (z-scores for local neigborhood dwelling density, street connectivity and daily living score) 

### street connectivity
- cleaned intersections (the number of cleaned intersections of pedestrain network/total area)

### dwelling density 
- standardized ratio of people or housing units within the city
- the number of dwellings within local walkable neighborhood/total area

### land use mix/daily living scores
- % of land use allocated to residential, retail, civic and institutional, entertainment, recreation, food-related (can we get the land use data?)
- access to POIs (e.g. convenience, supermarket, and public transport stop)
	- using the sausage buffer technique and binary measures =1 for at least one POI within the walkable neighborhood, =0 for no POI within the walkable neighborhood
	- using the [pandana approach](https://github.com/gboeing/urban-data-science/blob/59afcff905649c5f8d1f8256ec37f28496e0c740/20-Accessibility-Walkability/pandana-accessibility-demo-full.ipynb) for network accessibility and walkability analysis: nearest distance to POIs. 


** local walkable neighborhood: a 1600m walkable network buffered around pedestrain street  
** residentail neighborhood: 1600m pedestrain network buffer around residential addresses.   
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