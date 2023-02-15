# OpenStreetMap data

OpenStreetMap data are used to represent features of interest within regions of interest.

This can be retrieved in .pbf (recommended; smaller file size) or .osm format from sites including:

- https://download.geofabrik.de/
- http://download.openstreetmap.fr/extracts/
- https://planet.openstreetmap.org/pbf/  (whole of planet data; very large and not recommended)

It is recommended that a suffix to indicate publication date is added to the name of downloaded files as a record of the time point at which the excerpt is considered representative of the region of interest e.g. "las_palmas-latest.osm_20230210.pbf" or "oceania_yyyymmdd.pbf" where yyyy is the year, mm is the 2-digit numerical month, and dd is the 2-digit numerical day date_.

The main considerations that the excerpt is as small as possible while ensuring that it has complete coverage of the region(s) of interest (and about 1600 metres additional beyond the boundary, or as otherwise configured).  Using a smaller rather than a larger file will speed up processing.

For example, for a project considering multiple cities in Spain, the researchers could download an excerpt for the country of [Spain](https://download.geofabrik.de/europe/spain.html) or for specific sub-regions like [Catalunya](https://download.geofabrik.de/europe/spain/cataluna.html) as required to ensure that the region of interest is encompassed within the extract.  Using the example of Spain, which also contains regions outside Europe, if sourcing from Geofabrik as the example links above, it is worth noting that the excerpts are grouped by continent so some care should be taken.  For example, [Las Palmas de Gran Canaria](https://download.geofabrik.de/africa/canary-islands.html) are found under Canary Islands in Africa on Geofabrik, or a smaller PBF specifically for [Las Palmas](https://download.openstreetmap.fr/extracts/africa/spain/canarias/) can be retrieved from download.openstreetmap.fr under 'africa/spain/canarias'.

Metadata for the stored OpenStreetMap data should be recorded in datasets.yml.
