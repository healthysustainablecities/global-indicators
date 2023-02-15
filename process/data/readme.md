# Input and output data folders for the global-indicators software

This folder contains the input and output data folders for the GHSCI global-indicators software process.

## Input folders

When configuring your study region(s), some input data will be required.  Examples of required include a population grid, an excerpt from OpenStreetMap, and a study region boundary (either an administrative boundary, or an urban region from the Global Human Settlements Urban Centres Database).  Other data are optional: GTFS transit feed data, or a policy review analysis.

|Usage note    | Dataset folder     | Purpose        |
|--------------|--------------------|----------------|
|Required      | OpenStreetMap      | Representing features of interest |
|Required      | population_grids   | Representing population distribution |
|Conditional   | region_boundaries  | Identifying study region |
|Conditional   | urban_regions      | Identifying urban and/or study region |
|Optional      | policy_review      | Summarising results of a policy review analysis |
|Optional      | transit_feeds      | Collections of GTFS feeds to represent public transport service frequency |
|Optional      | other_custom_data  | Other custom data, such as points of interest |

Specific paths to data are configurable in the configuration files.  However, in general, input data is structured is recommended to be stored as follows:

data
    - OpenStreetMap
        - [_a .pbf or .osm excerpt of OpenStreetMap; should be dated with a suffix to indicate publication date e.g. "las_palmas-latest.osm_20230210.pbf" or "oceania_yyyymmdd.pbf" where yyyy is the year, mm is the 2-digit numerical month, and dd is the 2-digit numerical day date_]
    - population_grids
        -  [_a sub-folder with a descriptive name for a subset of tiles from GHSL or a national grid, e.g. "GHS_STAT_UCDB2015MT_GLOBE_R2019A" or "GHS_POP_P2030_GLOBE_R2022A_54009_100_V1_0"_]
            - [_one or more .tif files and associated metadata, e.g. "GHS_POP_P2030_GLOBE_R2022A_54009_100_V1_0_R14_C12.tif"_]
    - region_boundaries
        - [_optional subfolder for grouping boundary files, e.g. "Belgium"]
            - [_a specific file with the region boundary, e.g. "adminvector_3812.gpkg" or "ghent_3812.geojson"_]
        - [_a specific file with the region boundary (ie. optionally not in a sub-folder)]
    - urban_regions [_optionally, a study region can be defined by or restricted to a defined urban region from the Global Human Settlements Urban Centres Database_]
        - GHS_STAT_UCDB2015MT_GLOBE_R2019A_V1_2.gpkg
    - transit_feeds
        - [_some region specific GTFS parent folder, e.g. "Belgium"_]
            - [_one or more sub-folders containing unzipped files from GTFS feeds, e.g. de_lijn-gtfs_20230117, where the suffix indicates date of publication (feed metadata is also recorded in region config file)_]
    - policy_review (_in development_)
        - An Excel workbook grading policies corresponding to the policies configured in policies.yml

## Output folder

The results of analyses will be output to study region specific sub-folders within the following folder

_study_region_outputs
