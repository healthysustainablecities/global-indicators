Study region context
^^^^^^^^^^^^^^^^^^^^

The urban portion of the city of Ghent was defined as the intersection of its administrative boundary and the Global Human Settlements (GHS, 2019) urban centre layer for 2015 :cite:`ghs_ucl_data`.  Urban Ghent has an area of 74.58 km² and had a population estimate of approximately 174,411 persons in 2015, or 2,338.66 per km² :cite:`ghs_pop_method,ghs_pop_data`.

.. figure:: ../data/study_region/ghent_be_2020/ghent_be_2020_m_urban_boundary.png
   :width: 70%
   :align: center

   The intersection of administrative boundary (white outline) and urban centre (yellow shading) areas was used to define the study region (cross-hatching} used for analysis of liveability in Ghent.

.. figure:: ../data/study_region/ghent_be_2020/ghent_be_2020_m_popdens.png
   :width: 70%
   :align: center

   Spatial distribution of relative population density (estimated population per square kilometre) for Ghent.

Destinations
^^^^^^^^^^^^

Destinations sourced from OpenStreetMap (OSM) were identified using key-value pair tags.  Please see the :ref:`osm` section for more information, including links to guidelines for these categories and for country specific coding guidelines.


Fresh Food / Market
~~~~~~~~~~~~~~~~~~~


The following key-value tags were used to identify supermarkets, fresh food and market destinations using OpenStreetMap:

================ ==============
     Key              Value
================ ==============
shop             supermarket
supermarket      
amenity          supermarket
building         supermarket
shop             grocery
shop             bakery
shop             pastry
name             Tortillería
shop             butcher
shop             seafood
shop             fishmonger
shop             greengrocer
shop             fruit
shop             fruits
shop             vegetables
shop             deli
shop             cheese
amenity          marketplace
amenity          market
amenity          market_place
amenity          public_market
shop             marketplace
shop             market
================ ==============

Within a 500 metres Euclidean distance buffer of Ghent's urban study region boundary the count of Fresh Food / Market destinations identified using OpenStreetMap data was 221.

Please note that Euclidean distance analysis of destination counts was only undertaken in order to enumerate destinations within proximal distance of the city in order to produce this report; all indicators of access will be evaluated using network distance for sample points at regular intervals along the street network, prior to aggregation of estimates at small area and city scales.

.. figure:: ../data/study_region/ghent_be_2020/ghent_be_2020_m_fresh_food_market.png
   :width: 70%
   :align: center

   Destinations defined using key-value pair tags (listed above) were extracted from matching OpenStreetMap points or polygon centroids to comprise the category of 'Fresh Food / Market'.  Aggregate counts of destinations within each cell of a 250m hex grid was undertaken to illustrate the spatial distribution of the identified data points.



Convenience
~~~~~~~~~~~


The following key-value tags were used to identify convenience stores using OpenStreetMap:

================ ==============
     Key              Value
================ ==============
shop             convenience
amenity          fuel
shop             kiosk
shop             newsagent
shop             newsagency
amenity          newsagency
================ ==============

Within a 500 metres Euclidean distance buffer of Ghent's urban study region boundary the count of Convenience destinations identified using OpenStreetMap data was 188.

Please note that Euclidean distance analysis of destination counts was only undertaken in order to enumerate destinations within proximal distance of the city in order to produce this report; all indicators of access will be evaluated using network distance for sample points at regular intervals along the street network, prior to aggregation of estimates at small area and city scales.

.. figure:: ../data/study_region/ghent_be_2020/ghent_be_2020_m_convenience.png
   :width: 70%
   :align: center

   Destinations defined using key-value pair tags (listed above) were extracted from matching OpenStreetMap points or polygon centroids to comprise the category of 'Convenience'.  Aggregate counts of destinations within each cell of a 250m hex grid was undertaken to illustrate the spatial distribution of the identified data points.



Public transport stop (any)
~~~~~~~~~~~~~~~~~~~~~~~~~~~


It is planned to use General Transit Feed Specification (GTFS) data where available for public transport analysis.  However, GTFS data is not available for all cities, so additional analysis will be undertaken for all cities using OSM public transport data.

The following key-value tags were used to identify public transport stops using OpenStreetMap:

================ ==============
     Key              Value
================ ==============
public_transport platform
public_transport stop_position
highway          bus_stop
highway          platform
railway          platform
public_transport station
amenity          ferry_terminal
railway          tram_stop
railway          stop
================ ==============

Within a 500 metres Euclidean distance buffer of Ghent's urban study region boundary the count of Public transport stop (any) destinations identified using OpenStreetMap data was 1,368.

Please note that Euclidean distance analysis of destination counts was only undertaken in order to enumerate destinations within proximal distance of the city in order to produce this report; all indicators of access will be evaluated using network distance for sample points at regular intervals along the street network, prior to aggregation of estimates at small area and city scales.

.. figure:: ../data/study_region/ghent_be_2020/ghent_be_2020_m_pt_any.png
   :width: 70%
   :align: center

   Destinations defined using key-value pair tags (listed above) were extracted from matching OpenStreetMap points or polygon centroids to comprise the category of 'Public transport stop (any)'.  Aggregate counts of destinations within each cell of a 250m hex grid was undertaken to illustrate the spatial distribution of the identified data points.



Public open space
~~~~~~~~~~~~~~~~~


The identification of public open space using OpenStreetMap is a distinct question to other kinds of destinations which are usually localised as discrete 'points': public open space are areas (or polygons), and often may be quite large.    Parks, nature reserves, plazas and squares could all be considered areas of open space: open areas where people may gather for leisure.

Going into the full detail of the methods which we use to derive areas of open space using OpenStreetMap is beyond the scope of this report; however, the basic workflow is as follows:

Identify open space
###################

A series of logical queries are used to identify areas of open space; meeting any one of these is grounds for inclusion of consideration as a potential area of open space (noting that this may yet include private areas, which are not public open space). For example, any polygons with keys of 'leisure','natural','sport','beach','river','water,'waterway','wetland' with recorded values are recorded, in addition to specific combinations such as 'place=square'.   Other recorded combinations include 

* landuse, with values of: common, conservation, forest, garden, leisure, park, pitch, recreation_ground, sport, trees, village_green, winter_sports, wood, dog_park, nature_reserve, off_leash , sports_centre, 

* os_boundary, with values of: protected_area, national_park, nature_reserve, forest, water_protection_area, state_forest, state_park, regional_park, park, county_park

Exclusion criteria
##################

Any portions of the areas of the identified as being potential areas of open space which overlap areas identified as being 'excluded' are omitted from the open space dataset.

We create a polygon layer of areas which are categorically not to be considered as open space.  For example, if there is an area which has been coded to suggest it could be a natural area that might potentially be an open space (e.g. perhaps 'boundary=nature_reserve'), but actually is entirely within an area with a military or industrial land use, or is tagged to indicate that access is not public (e.g. for employees or staff only, private, or otherwise inaccessible): this is not an area of public open space and will be excluded.

Evaluating access
#################

Once areas of public open space have been identified, proxy locations for entry points are created at regular intervals (every 20 metres) on the sections of the boundaries of those areas of public open space which are within 30 metres of the road network.


.. figure:: ../data/study_region/ghent_be_2020/ghent_be_2020_m_pos.png
   :width: 70%
   :align: center

   For the city of Ghent, areas of public open space identified in Ghent have been plotted in green in the above map.



.. bibliography:: references.bib
    :style: unsrt


