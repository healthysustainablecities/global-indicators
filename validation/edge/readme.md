# Street Network Validation – Preliminary Result

Street networks obtained from OSM for three cities of Olomouc, Belfast, and Hong Kong are validated against the ones given by official collaborators from each city. 

The extent of the networks for validation is within the study area used by the project. 

Table 1 shows the networks from OSM and official networks for the three cities. For all three cities, OSM network tends to be denser. This is expected since OSM does include pedestrian paths. The official data might focus more on the major roads/street. Among the three cities, the difference between OSM and official networks are more visible in Hong Kong, an Asian city. Both Belfast and Olomouc datasets have street network down to the pedestrian level although the Belfast one seems to be more complete. However, the Hong Kong network is much more simple, mostly consists of only the major roads. Belfast and Olomouc are two European cities. European cities might collect more and make more of their data available for public. 

**Table 1: OSM and Official Street Network in three cities**
![Table 1: OSM and Official Street Network in three cities](results_file/networks_plot.png)

Total length of each network as well as number of segments are calculated to have a better comparison (Table 2). The total length of official dataset in Hong Kong is only about 40% of the OSM one. It is 40.3% in Olomouc and 78.2% in Belfast. The 2 datasets in Belfast are more similar than those in the other two cities. Similar pattern can be seen in the number of segments of the networks. Number of segment in official networks is about 71% of that of OSM network in Belfast. The number in Olomouc (29.2%) and Hong Kong (26.7%) are much lower. 

**Table 2: Results from comparing OSM and Official networks**

|  | Belfast OSM| Belfast Official | Olomouc OSM | Olomouc Official | Hong Kong OSM | Hong Kong Official |
| --- | --- | --- | --- | --- | --- | --- |
| Total Length (m) | 1700228.4 | 1330205.3 78.2% of OSM| 61691708 | 310456.1 50.3% of OSM | 7211707.9 | 2908824.6 40.3% of OSM |
 Number of segments | 26244 | 18662 71% of OSM | 14186 | 4149 29.2% of OSM | 108435 | 28953 26.7% of OSM |
| % intersected - 5m buffer |  | 80.8 | | 86.2 | | 87.0 |
| % intersected - 10m buffer |  | 87.3 | | 91.7 | | 95.6 |
| % intersected - 15m buffer |  | 90.9 | | 93.7 | | 97.6 |


We are interested in what type of areas where OSM and official datasets are different. Most importantly, in what area, OSM is missing a feature that are available in the official dataset. In order to do this, we overlay OSM network on top of the official one and investigate the gap in OSM network allowing feature from the official layer to be seen. The areas where the gaps happen are reviewed in Google Street map as well as Bing map in order to see the type of areas that OSM tends to miss. The findings are explained below. 

## Belfast: 
For Belfast, similar to the idea given by overviewing the network maps as well as calculating the rough number of network segment and total length, the OSM and official datasets are quite close. There are however, some small and disperse places where OSM network misses the feature available in the official one. Most of the missing features are internal network (of a property) Most of those places fall under these categories:

Places with dense canopy such as park: Figure 1 shows a castle with which OSM network misses all the paths within the property (in bright green). 

**Figure 1: Paths within a castle (in bright green)**

![Figure 1: Paths within a castle (in bright green)](results_file/figure1.jpg)

Industrial area: In figure 2, all the paths within a water plant (Veolia water) are missing in OSM street network. 

**Figure 2**

![Figure 2](results_file/figure2.png)

Internal network within residential areas: In Figure 3, OSM network misses the features within some residential areas. Paths that OSM tend to miss are the ones in shadow, which might prohibit the capturing of features and differentiation from the surrounding. 

**Figure 3**

![Figure 3](results_file/figure3.png)

## Olomouc:
The representation of street network in the official dataset is much simpler and reduced than in OSM especially a long highways and at major intersections. Figure 4.1a,b shows how an intersection looks like in OSM (brown) and in official data (blue). The OSM network is much more complete. 

**Figure 4.1a: OSM network**

![Figure 4.1a](results_file/figure41a.png)

**Figure 4.1b: official network**

![Figure 4.1b](results_file/figure41b.png)

However, the OSM does not fully show what exists in the official dataset. There are more gaps in OSM network in Olomouc than in Belfast. Moreover, the gaps are less scattered. They tend to cluster in the fringe area (Figure 4). 

Zooming more closely into these areas, we can see that most of them are internal network within industrial areas (blue lines in Figure 5)

**Figure 5: Internal network in industrial areas**

![Figure 5: Internal network in industrial areas](results_file/figure5.png)



## Hong Kong:

In the case of Hong Kong, the OSM dataset is much more inclusive than the official one. While OSM street network includes pedestrian level path, the official network only has the major roads. The official network is mostly covered by the OSM network. There are some few cases in which OSM did not have information as in the official one:

Internal path within a lot covered by lots of trees (Figure 6). The red segments in figure 6 shows official network while blue is the OSM network. Internal paths within the lot at the middle are only visible in red. 

**Figure 6**

![Figure 6](results_file/figure6.png)

A new developing segment as in Figure 7. Similar to figure 6, the red lines indicate official network while the blue ones are OSM network. We can see the whole trunk of major roads in the middle can only be seen in red (official dataset). From investigation of open source Hong Kong map, this section is a dead end, which is still being under development. The official network might be more updated in these cases of newly developed areas, especially in Asian countries where official data is less available to public.

**Figure 7**

![Figure 7](results_file/figure7.png)

## Area intersection of buffered networks:

Another step to better understand how well the OSM represents the official network is to calculate the area intersection between the 2 networks after buffering both by a certain distance. We choose to buffer both networks by various distance of 5m, 10m, and 15m and calculate the intersected (in what percentage of the area of the official network). By buffering, we hope to fix the issue that happens in all three cities, which is the imperfect alignment between the two networks but they are still close enough to count as the same. 

The results are presented in Table 2 above. We can see that the shared area account for high percentage of the official network area after buffering (over 80% in all cities with 5m buffer and over 90% in all cities with 15m buffer). This number shows that the official street network is relatively well represented by the OSM network. 

## Importance of some gap in OSM network to the study of accessibility

As we have found, there exist some places where OSM network does not fully represent the official dataset. These are likely due to dense covering of trees, shadows of buildings, newly developed areas.  However, the more important question is whether that hurt our understanding of urban accessibility using OSM network. 

Most of the gaps in OSM network happen with internal network (within a property, an industrial area). This won't affect the understanding of how easy people to access goods and facilities in a neighborhood or outside. Moreover, many of the gaps are found in industrial areas, newly developed areas, or places with very low residential density (like castle). As the result, the gaps are of less importance to our study. 

Overall, we can argue that OSM network is a valid and reliable data source to represent the official street network. 
