# Data sources and licences

Every dataset in this folder is an excerpt of an openly licensed source,
reduced in size so that a complete worked example can be distributed with the
software. Nothing here is original data.

`scripts/prepare_example_data.py` records exactly how each excerpt was derived
and can regenerate them all.

Attribution requirements travel with the data. If you reuse an excerpt, or a
result derived from one, credit the source as set out below.

---

## Boundaries

**`boundaries/las_palmas_municipality.geojson`** — the municipal boundary of
Las Palmas de Gran Canaria, used as the study region boundary.

- Source: Centro Nacional de Información Geográfica, *Líneas límite
  municipales* (`lineas_limite.zip`)
- URL: https://datos.gob.es/en/catalogo/e00125901-spaignllm
- Published: 2019-02-01
- Licence: CC BY 4.0
- Citation: Instituto Geográfico Nacional (2019). *Base de datos de divisiones
  administrativas de España.*
  https://datos.gob.es/en/catalogo/e00125901-spaignllm
- Derivation: the municipal boundary was extracted from the national release
  and reprojected to WGS84 (EPSG:4326). Municipal boundaries are stable, so
  this excerpt is carried over unchanged from the superseded 2023 example
  rather than re-cut from the national download.

**`boundaries/school_districts.geojson`** — secondary school catchment areas,
used to demonstrate aggregation to custom areas.

- Source: Gobierno de Canarias open data portal, *Centros educativos — áreas de
  influencia de centros de secundaria*
- URL: https://opendata.sitcan.es/dataset/centros-educativos/resource/ea650255-c6ea-48c1-84e8-547735624017
- Last updated: 31 May 2023
- Licence: CC BY 4.0
- Derivation: catchments intersecting Las Palmas de Gran Canaria were extracted
  from the Canary Islands dataset.

---

## Population

**`population/ghsl_100m/GHS_POP_E2025_GLOBE_R2023A_54009_100_V1_0_R6_C17.tif`**
— modelled residential population, 100 m grid, 2025 epoch.

- Source: European Commission, Joint Research Centre — Global Human Settlement
  Layer, GHS-POP R2023A
- URL: https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_POP_GLOBE_R2023A/GHS_POP_E2025_GLOBE_R2023A_54009_100/V1-0/tiles/GHS_POP_E2025_GLOBE_R2023A_54009_100_V1_0_R6_C17.zip
- Licence: CC BY 4.0
- Citation: Schiavina, Marcello; Freire, Sergio; Alessandra Carioli; MacManus,
  Kytt (2023): *GHS-POP R2023A - GHS population grid multitemporal
  (1975-2030).* European Commission, Joint Research Centre (JRC) [Dataset]
  doi: 10.2905/2FF68A52-5B5B-4A22-8F40-C41DA8332CFE
- Derivation: tile R6_C17 (which covers the Canary Islands) was clipped to the
  2500 m buffered municipal boundary, in the source Mollweide projection so
  that no resampling occurs. The clip holds ~485,000 people.

---

## Urban region

**`urban_region/GHS_UCDB_R2024A_Las_Palmas.gpkg`** — the Las Palmas de Gran
Canaria urban centre, used to restrict analysis to the urban area.

- Source: European Commission, Joint Research Centre — Global Human Settlement
  Layer Urban Centre Database, GHS-UCDB R2024A
- URL: https://human-settlement.emergency.copernicus.eu/ghs_ucdb_2024.php
- Licence: CC BY 4.0
- Citation: Pesaresi, M., Schiavina, M., Politis, P., Freire, S.,
  Krasnodębska, K., Uhl, J. H., … Kemper, T. (2024). Advances on the Global
  Human Settlement Layer by joint assessment of Earth Observation and
  population survey data. *International Journal of Digital Earth*, 17(1).
- Derivation: the single record where `GC_UCN_MAI_2025 = 'Las Palmas de Gran
  Canaria'` and `GC_CNT_GAD_2025 = 'Spain'` was extracted from the
  `GHS_UCDB_THEME_GENERAL_CHARACTERISTICS_GLOBE_R2024A` layer of the full
  273 MB database, and written under that same layer name with every
  attribute retained, so that the excerpt is a scaled down replica of the
  distributed geopackage rather than a simplified abstraction of it. The
  region configuration therefore selects the centre from it with the same
  `-where` query that would be used against the full database. The urban
  centre covers 51 km² and 378,494 people.

---

## OpenStreetMap

**`openstreetmap/las_palmas-260728.osm.pbf`** and its `.poly` boundary filter —
the street network, destinations and open space used throughout the analysis.

- Source: OpenStreetMap contributors, via the OpenStreetMap.fr Canary Islands
  extract
- URL: https://download.openstreetmap.fr/extracts/africa/spain/canarias/las_palmas-latest.osm.pbf
- Snapshot: 28 July 2026
- Licence: **Open Database Licence (ODbL) 1.0**
- Derivation: the 59 MB Canary Islands extract was clipped with `osmconvert` to
  the 2500 m buffered municipal boundary, giving 4 MB.

**The ODbL is a share-alike licence.** Any derivative database produced from
this extract — including the GeoPackage this analysis writes — carries the
same obligations. Credit "© OpenStreetMap contributors".

---

## Public transport

**`gtfs/gtfs_es_las_palmas_guaguas.zip`** — scheduled bus services, used for
the public transport access and service frequency indicators.

- Source: Guaguas Municipales, the municipal bus operator
- URL: https://www.guaguas.com/transit/google_transit.zip
- Licence: published by the operator for public reuse in the GTFS format; no
  separate licence statement is distributed with the feed. Credit Guaguas.
- Derivation: the published feed was repacked to drop the `__MACOSX/` resource
  fork entries it ships with; the GTFS tables themselves are unmodified. The
  feed contains 47 bus routes from a single agency.
- Analysis window: 5 April to 5 June 2025, chosen because every service in
  `calendar.txt` runs from 2015 to 2035 and no `calendar_dates.txt` exception
  falls within that period, so it represents ordinary scheduled service.

---

## Policy review

**`policy/gohsc-policy-indicator-checklist-example-ES-Las-Palmas.xlsx`** — a
completed policy indicator checklist, used to demonstrate the policy report.

- Source: Global Observatory of Healthy and Sustainable Cities
- Licence: CC BY 4.0
- Note: this is an illustrative, partially completed checklist prepared for
  demonstration. It is **not** an authoritative assessment of policy in Las
  Palmas de Gran Canaria and should not be cited as one.

---

## Imagery

**`images/*.jpg`** — four generic illustrations used on the report cover pages.

- Source: generated with Bing Image Creator for the Global Observatory of
  Healthy and Sustainable Cities, credited in the region configuration
- Note: these are **placeholders**, not photographs of Las Palmas de Gran
  Canaria. When configuring a real study region, replace them with imagery of
  that city and update the credits in the region configuration.

---

## This folder

The scripts, region configuration files and notebook here are released under
the MIT Licence, consistent with the GHSCI software. See
[LICENCE.md](LICENCE.md).
