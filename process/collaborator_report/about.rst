.. _about:

About this report
~~~~~~~~~~~~~~~~~

Progress is being made on creating the indicators for the 25 cities included in the study.  In order to do that, we need your help (see :ref:`feedback` for a link to a short Google Form).  In the first part of this short report, we describe the process we are undertaking.  Then we outline the questions we need answers to, before providing you with summary results so far for your city, which we request that you review.

.. _aims:

Summary of aims for spatial indicators study
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Responding to a challenge to establish 'a set of indicators to benchmark and monitor progress towards achievement of more compact cities that promote health and reduce health inequities' :cite:`giles-corti2016`, and complementing a concurrent policy analysis study, the spatial analysis component of the Global Liveability Indicators project aims to develop a suite of policy relevant spatial indicators of liveability for urban areas of 25 diverse cities, globally.

Indicators will be produced based on network analysis of sample points in urban areas of cities, with two output scales: a 250 metre hexagonal grid (for plotting the within city spatial distribution of measures); and city level summary.

The set of indicators chosen for calculation include:

* A walkability index (within city, and between city versions)

* percent of population with access to frequent* public transport within 500 metres (* where frequency data is available)

* percent of population with access to public open space

Walkability is calculated as a composite score using local neighbourhood measures of population density, street connectivity, and land use mix.  We use a score for proximal access to daily living amenities (fresh food, convenience, and public transport) as proxy measure for land use mix  :cite:`arundel2017,mavoa2018` , which would otherwise be a challenge to calculate on a global scale.  

This report concerns the data sources used to calculate the above measures and/or their components, and more detail around these data sources and the methods of calculation is provided below.


Defining study regions
~~~~~~~~~~~~~~~~~~~~~~

The analysis area for each city included in the Global Liveability Indicators project was constructed using the intersection of a city administrative boundary (supplied by collaborators via a Google Form survey or acquired by the researchers independently) and `urban centres <https://ghsl.jrc.ec.europa.eu/ghs_stat_ucdb2015mt_r2019a.php>`_ identified by the Global Human Settlements project :cite:`ghs_ucl_data` .  

The use of an independent, global data source for urban centres helps to ensure that the analysis focus on exposure for urban populations across all cities, and not for example for lower density rural settings on the urban fringe, which may otherwise fall within an administrative boundary.

A large buffer (10 kilometres) was created around each study region, which defined the broader area of analysis for access to amenities.  Built environment data --- the network of roads and paths accessible by the public, and a series of destinations --- were acquired for each city within the respective buffered study region boundaries.  

The use of a buffer such as this ensures that the population who may live on the edge of the identified urban study region can still have access to nearby amenities evaluated, even if located outside the identified urban bounds.  Access will only be analysed up to 500 metres network distance for the present set of indicators, however the broader buffer area allows us flexibility for expanding analysis in the future.  

.. _osm:

Using OpenStreetMap for destination data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When comparing diverse cities globally, three key data concerns are: 1) consistency of coding across cities, 2) completeness of data across cities, and 3) appropriateness of data for local context.  

The Global Indicators project makes use of OpenStreetMap data, a publicly accessible global dataset of road and path networks, as well as destinations --- fresh food or markets, convenience stores, public transport stops or stations, and public open space.  OpenStreetMap is a collaborative mapping platform with an open data ethos launched in 2004 and has more than 5 million users globally (`wikipedia <https://en.wikipedia.org/wiki/OpenStreetMap>`_ ); it is an important source for consistently coded road network data globally.  With estimated completeness of coverage being very high for urban areas with favourable comparisons to comparable road datasets :cite:`barringtonleigh2017`, there are established tools for using it in geospatial urban transport analysis :cite:`boeing2017`.

There are also established guidelines for tagging destinations in OpenStreetMap using English or bilingually, for specific types of destinations of interest to our study:

* `Supermarkets <https://en.wikipedia.org/wiki/Supermarket>`_ (commonly used in built environment analysis as a primary source of fresh food)

* `Markets <https://wiki.openstreetmap.org/wiki/Tag:amenity%3Dmarketplace>`_ (which may be a major source of fresh food in some locations of some cities)

* `Shops <https://wiki.openstreetmap.org/wiki/Key:shop>`_, in general (which may include bakeries, or other specific locations selling fresh food)

* `Convenience stores <https://wiki.openstreetmap.org/wiki/Tag:shop%3Dconvenience>`_ (where basic and non-essential items may be acquired)

* `Public transport <https://wiki.openstreetmap.org/wiki/Public_transport>`_ (which might include bus, tram/light rail, train/metro/rail, ferry, etc)

* Public open space, including '`green space <https://wiki.openstreetmap.org/wiki/Green_space_access_ITO_map>`_', '`squares <https://wiki.openstreetmap.org/wiki/Tag:place%3Dsquare>`_', or other kind of public area for `pedestrians <https://wiki.openstreetmap.org/wiki/Tag:highway%3Dpedestrian>`_

The above guidelines were consulted along with `OSM TagInfo <https://taginfo.openstreetmap.org/>`_ to identify a set of appropriate tags which collectively are used define sets of destinations belonging to each of these categories.  These definitions are provided later in this document.  A tag is a way which contributors to OSM mark data using combinations of terms called key-value pairs.  This concept is explained in more detail below.

Where a destination in the real world does not appear in our extract of the OSM data, there are two reasons this might be the case; either there is no information whatsoever on the destination in OSM (it has not been entered by an OSM contributor), or alternatively the way the destination is tagged means that we have not picked it up during the extraction process.

The Health Liveable Cities group has audited the use of OpenStreetMap for our liveability work in Australia, and like other researchers, we have found it broadly acceptable for use in our urban contexts.   For the Global Indicators study, we encourage our collaborators to consider the results for their city and provide us with feedback.

.. _feedback:

We request your feedback
~~~~~~~~~~~~~~~~~~~~~~~~

Destination counts and distribution maps for your city will be provided below, followed by the tags used for coding.  `OSM TagInfo <https://taginfo.openstreetmap.org/>`_ can be used to query the usage of a 'key' like '`shop <https://taginfo.openstreetmap.org/keys/shop>`_', or a value associated with a key like: shop = `supermarket <https://taginfo.openstreetmap.org/tags/shop=supermarket>`_.  Using this website, you can also view a `map of the global distribution <https://taginfo.openstreetmap.org/tags/shop=supermarket#map>`_ of such tags.  If you want to view the spatial distribution of tagging in a particular country in detail, you can click the 'Overpass turbo' button, which will load up a map on the right hand side of a window and some code in the left hand side; drag and zoom or search for your area of interest and then click 'Run' the code.  Any locations tagged in this way in this location will be displayed.  You can click on a particular location to view additional tags that may have been coded, in addition to the one which you initially queried.

There are also applied `guidelines <https://wiki.openstreetmap.org/wiki/Category:Tagging_guidelines_by_country>`_ available for many countries/regions.

Given your knowledge of local context and alternative available public datasets

* Are there additional tags to those listed below, which you would recommend we consider including to improve identification of locations in your city?

* If you have not already done so, could you provide alternative spatial data which could be used for undertaking validation of OpenStreetMap data in your city?

* Do you have other comments?

A Google form has been set up to receive answers from project collaborators for the above questions.  Please provide your responses using the linked form, `here <https://forms.gle/22oz2CojgVLadueW7>`_.