# Study region outputs

The results of analyses will be output to study region specific sub-folders within this folder.

The sub-folders have a naming schema reflecting the convention:

[city code name]_[2-letter country code]_[yyyy]

For example, ghent_be_2020 or valencia_v2_es_2020.

Following completion of successful processing of a study region, the following provides an indication of the contents of this folder:

|Item                                                            | Type | Description |
|----------------------------------------------------------------|------|-------------|
|_web reports                                                    | Folder| Contains generated policy and spatial indicator reports, optionally in multiple languages|
|figures                                                         | Folder| Contains generated maps and figures|
|_01_create_study_region.log                                     | text file| A text file that is progressively appended to with the screen outputs for analyses that are not otherwise displayed.  This contains a record of processing, and is useful when debugging if something has gone awry with a particular configuration or supplied data|
|poly_li_valencia_v2_2020.poly                                   | text file| A polygon boundary file; this is generated for the buffered urban region of interest as per configuration in regions.yml, and is used to excerpt a portion of OpenStreetMap for this region from the configured input data|
|population_100m_2020_valencia_v2_25830.tif                      | raster image| A population raster for this buffered study region, excerpted from the input data, in the projects coordinate reference system |
|population_100m_2020_valencia_v2_ESRI54009.tif                 | raster image| A population raster for this buffered study region, excerpted from the input data, in the coordinate reference system of the input population data (e.g. Mollweide, in the case of the recommended GHS-POP data) |
|valencia_v2_es_2020_1600m_buffer.gpkg                           | geopackage| A geopackage containing derived study region features of interest used in analyses, and including grid and overall summary results for this region |
|valencia_v2_es_2020_1600m_pedestrian_osm_20221015.graphml       | graphml| A graphml representation of the derived routable pedestrian network for this buffered study region |
|valencia_v2_es_2020_1600m_pedestrian_osm_20221015_proj.graphml  | graphml| A graphml representation of the derived routable pedestrian network for this buffered study region, projected with units in metres |
|valencia_v2_es_2020_city_2023-02-15.csv                         | CSV file| Overall summary results of indicator analysis for this region |
|valencia_v2_es_2020_grid_100mm_2023-02-15.csv                   | CSV file| Grid summary results of indicator analysis for this region |
|valencia_v2_osm_20221015.pbf                                    | PBF file| An excerpt from OpenStreetMap for this buffered study region as configured |
