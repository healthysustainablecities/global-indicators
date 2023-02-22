# GTFS transit feed data

Collections of GTFS feeds are used to represent public transport service frequency.  More than one transit operator may operate in the region of interest, so it is important to aim to have full coverage of both the region and the operators, without overlap of services, to represent the service frequency of public transport stops in a city.

Transit feed data may be available from Government open data portals, or otherwise from aggregator sites such as https://transitfeeds.com/ and https://www.transit.land/.

We recommend that feeds be stored in a region specific GTFS parent folder, e.g. "Spain - Valencia", that contains one or more sub-folders containing unzipped files from GTFS feeds, e.g. gtfs_spain_valencia_EMT_20190403 and gtfs_spain_valencia_MetroValencia_20190403, where the suffix indicates date of publication.

Metadata for the stored GTFS transit feed data should be recorded in regions.yml.
