# Public transport stops with regular daytime weekday service - with GTFS data
The details provided below are historical and relate to v1.0.0 or earlier of the GHSCI software.  These may later be updated, but references to code are no longer current.  The document is provided for reference purposes only.

## Method
The headway analysis (`12_all_cities_gtfs_analysis.py`) generates a geopackage with stop location layers for each study region, associated day time weekday headways.  Headways for each stop were evaluated as the minimum average service frequencies for trips in either direction by any mode servicing the stop for weekdays (Mon-Fri) between 7am and 7pm during a late Spring period, chosen to avoid school holidays and unseasonable winter weather which could impact schedules and fair comparisons for some study regions. It extends methods used by the Healthy Liveable Cities group for analysis of public transport in Australian cities (Arundel J, Lowe M, Hooper P, Roberts R, Rozek J, Higgs C, et al. Creating liveable cities in Australia: Mapping urban policy implementation and evidence-based national liveability indicators. RMIT University; 2017. https://apo.org.au/node/113921; and the 2018 National Liveability project, data and methods publication forthcoming).

There are two steps to conducting the analysis:

1. Set up study region GTFS analysis parameters (`process/data/GTFS/gtfs_config.py`)
2. Run the analysis code `python 12_all_cities_gtfs_analysis.py`

As a result of running the code, a summary of the GTFS headway analysis is output to `../data/GTFS/all_cities_comparison_{today}.csv`, and a geopackage of public transport stop locations with associated average daytime weekday headways:
`../data/GTFS/gtfs_frequent_transit_headway_{today}_python.gpkg`

The analysis script loads GTFS data into an UrbanAccess transit data frame, restricted to a bounding box for the buffered study region.  Headway analysis is conducted using average departure frequency during usual weekday (Monday-Friday) daytime (7am-7pm) for all configured feeds (one city can have more than one feeds) and modes of transport.

### What is a “public transport stop”?
- The modes of public transport included are as per the GTFS specification for the `route_type` variable at https://developers.google.com/transit/gtfs/reference#routestxt : tram, metro, rail, bus, ferry, cable tram, aerial lift, funicular, trolleybus and monorail.
- Not all agencies strictly follow the GTFS specification, and so configuration allows some flexibility for mapping route type codes to modes of transport.

### Which stop qualify as regular service on a daily basis?
- Operates during normal day time from 7am to 7pm
- Operates during usual weekday (Monday to Friday) during the time period of interest for that city

### How to define a “usual weekday”?
- We aimed to use feeds from 2019 with coverage of a common time of year, avoiding major holiday periods (i.e. Spring-Summer school term time) to ensure comparability and consistency as much as possible.
    - 5 April to 5 June for Northern Hemisphere cities
    - 8 October to 5 December for those in the Southern Hemisphere
- Not all schedules neatly met this criteria depending on the availability of the feeds data.  However, any mismatch should be accounted for when interpreting results.

## Set up and run the analysis

### Retrieve and locate GTFS data in `process/data/GTFS/gtfs_input_data`
The folder `process/data/GTFS/gtfs_input_data` in this repository is used to store folders containing GTFS feed files for each study region used for the analysis. The table below summarises the GTFS resources used in the Global Indicators project.

First, create a subfolder named `gtfs_country_jurisdiction` (e.g. gtfs_us_seattle) within the `gtfs_input_data` folder. Download and extract the study region GTFS zip file to a folder `gtfs_country_jurisdiction_agency_yyyymmdd` (e.g. gtfs_au_sa_adelaidemetro_20191004.zip; yyyymmdd represents the start date of the GTFS feed.


| Region         | Country          | City        | Feed # | URL                                                                                                          | Agency / Provider                  | Year | Analysis start yyyy-mm-dd   | Analysis end yyyy-mm-dd   |
|----------------|------------------|-------------|:------:|--------------------------------------------------------------------------------------------------------------|------------------------------------|------|:---------------------------:|:-------------------------:|
| America, North | Mexico           | Mexico City |    1   | https://transitfeeds.com/p/mexico-city-federal-district-government/70/20190109/download                      | FederalDistrictGovernment          | 2019 |          2019-04-05         | 2019-06-05                |
| America, North | United States    | Baltimore   |    1   | https://transitfeeds.com/p/mta-maryland/247/20190408/download                                                | MarylandMTA                        | 2019 |          2019-04-05         | 2019-06-05                |
| America, North | United States    | Phoenix     |    1   | https://transitfeeds.com/p/valley-metro/68/20190403/download                                                 | Valleymetro                        | 2019 |          2019-04-05         | 2019-06-05                |
| America, North | United States    | Seattle     |    1   | https://transitfeeds.com/p/king-county-metro/73/20190320/download                                            | KingCountyMetro                    | 2019 |          2019-04-05         | 2019-06-05                |
| America, South | Brazil           | São Paulo   |    1   | https://transitfeeds.com/p/sptrans/1049/20190404/download                                                    | SPTrans                            | 2019 |          2019-10-08         | 2019-12-05                |
| Asia           | Thailand         | Bangkok     |    1   | https://namtang-api.otp.go.th/download/namtang-gtfs.zip                                                      | OTP Namtang Open Data portal       | 2021 |          2021-04-05         | 2021-06-05                |
| Asia           | Hong Kong SAR    | Hong Kong   |    1   | https://data.gov.hk/en-data/dataset/hk-td-tis_11-pt-headway-en                                               | data.gov.hk                        | 2019 |          2019-04-05         | 2019-06-05                |
| Asia           | India            | Chennai     |    1   | http://www.gtfs-data-exchange.com/agency/metropolitan-transport-corporation/                                 | Metropolitan Transport Corporation | 2010 |          2010-04-05         | 2010-06-05                |
| Asia           | India            | Chennai     |    2   | https://github.com/justjkk/chennai-rail-gtfs                                                                 | J Kishore Kumar (Github user)      | 2016 |          2016-10-08         | 2016-12-05                |
| Asia           | Vietnam          | Hanoi       |    1   | https://datacatalog.worldbank.org/dataset/hanoi-vietnam-general-transit-feed-specification-gtfs              | World Bank                         | 2018 |          2018-04-05         | 2018-06-05                |
| Asia           | Vietnam          | Hanoi       |    2   | https://datacatalog.worldbank.org/dataset/hanoi-vietnam-general-transit-feed-specification-gtfs              | World Bank                         | 2018 |          2018-04-05         | 2018-06-05                |
| Asia           | Vietnam          | Hanoi       |    3   | https://datacatalog.worldbank.org/dataset/hanoi-vietnam-general-transit-feed-specification-gtfs              | World Bank                         | 2018 |          2018-04-05         | 2018-06-05                |
| Australasia    | Australia        | Adelaide    |    1   | https://transitfeeds.com/p/adelaide-metro/1/20191004/download                                                | AdelaideMetro                      | 2019 |          2019-10-08         | 2019-12-05                |
| Australasia    | Australia        | Melbourne   |    1   | https://transitfeeds.com/p/ptv/497/20191004/download                                                         | PublicTransportVictoria            | 2019 |          2019-10-08         | 2019-12-05                |
| Australasia    | Australia        | Sydney      |    1   | https://data.gov.au/dataset/ds-nsw-30943035-80de-4fe2-b4d3-9de606147f31/details?q=GTFS                       | NSW                                | 2019 |          2019-10-08         | 2019-12-05                |
| Australasia    | New Zealand      | Auckland    |    1   | https://transitfeeds.com/p/auckland-transport/124/20191001/download                                          | AucklandTransport                  | 2019 |          2019-10-08         | 2019-12-05                |
| Europe         | Czechia          | Odense      |    1   | https://transitfeeds.com/p/rejseplanen/705/20190404                                                          | https://www.rejseplanen.dk/        | 2019 |          2019-04-05         | 2019-06-05                |
| Europe         | Germany          | Cologne     |    1   | https://transitfeeds.com/p/comboios-de-portugal/1004/20190403/download                                       | VRS                                | 2018 |          2018-04-05         | 2018-06-05                |
| Europe         | Northern Ireland | Belfast     |    1   | https://data.nicva.org/dataset/translink-bus-timetables-gtfs/resource/b98fbd78-01d8-4e93-9bc0-86a3d566feb7   | Translink                          | 2017 |          2017-04-05         | 2017-06-05                |
| Europe         | Portugal         | Lisbon      |    1   | https://transitfeeds.com/p/carris/1000/20190403/download                                                     | Carris                             | 2019 |          2019-04-05         | 2019-06-05                |
| Europe         | Portugal         | Lisbon      |    2   | https://transitfeeds.com/p/metro-de-lisboa/1003/20190403/download                                            | Metro de lisboa                    | 2019 |          2019-04-05         | 2019-06-05                |
| Europe         | Portugal         | Lisbon      |    3   | https://transitfeeds.com/p/fertagus/1001/20190403/download                                                   | Fertagus                           | 2019 |          2019-04-05         | 2019-06-05                |
| Europe         | Portugal         | Lisbon      |    4   | https://transitfeeds.com/p/transportes-sul-do-tejo/999/20190403/download                                     | MTS                                | 2019 |          2019-04-05         | 2019-06-05                |
| Europe         | Portugal         | Lisbon      |    5   | https://transitfeeds.com/p/soflusa/1002/latest/download                                                      | Soflusa                            | 2019 |          2019-04-05         | 2019-06-05                |
| Europe         | Portugal         | Lisbon      |    6   | https://transitfeeds.com/p/transtejo/1006/20190403/download                                                  | Transtejo                          | 2019 |          2019-04-05         | 2019-06-05                |
| Europe         | Portugal         | Lisbon      |    7   | https://transitfeeds.com/p/comboios-de-portugal/1004/20190403/download                                       | CP                                 | 2019 |          2019-04-05         | 2019-06-05                |
| Europe         | Spain            | Barcelona   |    1   | https://transitfeeds.com/p/amb-mobilitat/994/20190404/download                                               | AMB                                | 2019 |          2019-04-05         | 2019-06-05                |
| Europe         | Spain            | Barcelona   |    2   | https://transitfeeds.com/p/transports-metropolitans-de-barcelona-tmb/995/20190402/download                   | TMB                                | 2019 |          2019-04-05         | 2019-06-05                |
| Europe         | Spain            | Barcelona   |    3   | https://transitfeeds.com/p/tram-trambaix/996/20190303/download                                               | TMB                                | 2019 |          2019-04-05         | 2019-06-05                |
| Europe         | Spain            | Valencia    |    1   | https://transitfeeds.com/p/ferrocarriles-de-la-generalidad-valenciana/1039/20190403/download                 | MetroValencia                      | 2019 |          2019-04-05         | 2019-06-05                |
| Europe         | Spain            | Valencia    |    2   | https://transitfeeds.com/p/emt-valencia/719/20190403/download                                                | EMT                                | 2019 |          2019-04-05         | 2019-06-05                |
| Europe         | Switzerland      | Bern        |    1   | https://opentransportdata.swiss/en/dataset/timetable-2019-gtfs/resource/052d3047-de64-4461-b905-36642fb58de8 | opentransportdata.swiss            | 2019 |          2019-04-05         | 2019-06-05                |

### Set up study region GTFS analysis parameters in `process\data\GTFS\gtfs_config.py`:
Check `process\data\GTFS\gtfs_config.py` for the example used in the Global Indicators project.  The GTFS specification is loosely followed by transport agencies when publishing GTFS data and some customisation of parameters may be required to ensure that estimated headway is operationalized appropriately.

### Run the analysis script:
```
python gtfs_headway_analysis.py
```

#### Or run this notebook `GTFS_headway_analysis.ipynb` for an individual city analysis

## Outputs

A summary of the GTFS headway analysis is saved to `../data/GTFS/all_cities_comparison_{today}.csv`, and a geopackage of public transport stop locations with associated average daytime weekday headways is saved to `../data/GTFS/gtfs_frequent_transit_headway_{today}_python.gpkg`.
