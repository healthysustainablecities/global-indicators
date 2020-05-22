# Preliminary Findings:

Points of interest (freshfood and market) obtained from OSM for three cities of Olomouc, Belfast, and Sao Paulo are validated against the ones given by official collaborators from each city. 
Table 1 shows the summary of the datasets including datatype, size of the datasets, definitions of what were presented, as well as the intersection between OSM and official datasets of each city. 

We can see the three cities are very different in terms of the number of official fresh food points as well as how those points are captured by OSm. Olomouc has less fresh food related points than the other two cities, which is reasonable due to its smaller size. Moreover, the difference between the number of points in OSM and Official datasets in Olomous is much less than that in the other cities. OSM dataset has 4 more points than the official one. The OSM dataset in Sao Paulo is more than twice the size of the official one. On the other hand, OSM in Belfast covers only less than 10% of the points in the official datasets. This is due to the different definition of fresh food related. This information is in the last row of Table 1. Official fresh food related points in Belfast also include restaurants, which are not available in the OSM points leading to the much higher number of official points. Official data in Olomouc, while only includes supermarkets, is roughly the number of points in the OSM list, suggesting supermarkets are the main destinations for fresh food in this city. The interesting thing is in the case of Sao Paulo, while the official set includes many different forms of market including street market, which can be periodic features, not available in the OSM, the official dataset is still much smaller than the OSM one. These observations need further investigation by looking closely at the mismatched points. 

Instead of point features, official dataset in Belfast shows the polygon representation of the fresh food related features. According to the collaborator, these polygons are the parcels within which the pointers of fresh food related destination exist. However, the polygons dataset might be less updated than the pointer dataset. 


**Table 1: OSM and Official Fresh food related points of interest in three cities**


|  | Belfast OSM| Belfast Official | Olomouc OSM | Olomouc Official | Sao Paulo OSM | Sao Paulo Official |
| --- | --- | --- | --- | --- | --- | --- |
| Number of points | 124 | 1479| 67 | 63 | 2132| 939 |
| Number of intersected points | 26 | 26 | 0 | 0 | 0 | 0 |
| Type of data | points  |polygons | points | points | points | points |
| Features included | Market, grocery, convenience store |Freshfood and Restaurant related|Market, grocery, convenience store | Supermarkets|Market, grocery, convenience store | street markets, municipal markets, municipal restaurants, grocery bigbags |

**Intersections and buffering: **

From Table 1 we can see that the number of official points intersected with the OSM dataset is very low in all three cities (26 in Belfast, and 0 in the other 2 cities). However, this might be due to the fact that these are mainly point representation of polygon features (shops/ market etc.) In the case of Sao Paulo street market, it can also be point representation of linear feature. 

The three following sections summarize the findings from investigation of OSM and Official fresh food POIs with reference to Bing Map and google street map. What we are interested is that where OSM misses a point that is available in the Official dataset, what might be the reason. 

### 1. Belfast:
     
     number of OSM points:  124 - Fresh food and market POINTS
     
     number of Official points:  1479 - Food and Restaurant Related POLYGONS
     
     number of intersection items:  26
     
     Percentage:  20.967741935483872
    
    {'init': 'epsg:29903'} vs 29902 

    
    100m buffering of Official points:
       
       intersection:  95
       
       percent of OSM points 76.61290322580645

     
     100m buffering of OSM points:
       
       intersection:  392
       
       percent of Official Point:  26.504394861392832

     Nearest distance histogram: belfast_nearest_distance.png
     Mean nearest distance: 373.26237858661005
     Median nearest distance: 36.93827942430583
     
     Some noted problems: 
       
       Mismatched definitions (restaurants included or not?)
       Official points as POLYGONS (of city block size) - confirming with collaborators
       Unmatched crs between what's in the official dataset and the one used for OSM

### 2. Sao Paulo

     number of OSM points:  2132 - Fresh food and market POINTS
     
     number of Official points:  939 - street markets, municipal markets, municipal restaurants, grocery bigbags POINTS
     
     number of intersection items:  0
     
     Percentage:  0.0
    
    {'init': 'epsg:31983'} vs 32723

    
    100m buffering of Official points:
       
       intersection:  487
       
       percent of OSM points: 22.842401500938088 

     
     100m buffering of OSM points:
       
       intersection:  205
       
       percent of Official Point: 21.831735889243877

     Nearest distance histogram: sao_paulo_nearest_distance.png
     Mean nearest distance: 1416.304145492677
     Median nearest distance: 248.37187706365415
     
     Some noted problems:
         
        Street markets: - periodic markets, linear features represented in points
        Unmatched crs between what's in the official dataset and the one used for OSM
        

### 3. Olomouc

     number of OSM points:  67
     
     number of Official points:  63
     
     number of intersection items:  0
     
     Percentage:  0.0
    
    {'init': 'epsg: 5513'} vs 32633

    
    100m buffering of Official points:
       
       intersection:  45
       
       percent of OSM points : 67.16417910447761

     
     100m buffering of OSM points:
       
       intersection:  46
       
       percent of Official Point:  73.01587301587301

     Nearest distance histogram: olomouc_nearest_distance.png

