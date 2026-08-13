---
layout: default
title: Custom data
permalink: /Custom-data/
---

# Custom data

By default, the software identifies destinations and public open space from OpenStreetMap, and generates sample points along the pedestrian network wherever there is population data coverage.  Each of these can be supplemented or replaced with your own data, which may be preferable where an authoritative local dataset exists, or where OpenStreetMap coverage of your city is incomplete.

This page covers three optional sections of the study region configuration file:

- [`points_of_interest`](#custom-points-of-interest) — your own destination data
- [`public_open_space`](#custom-public-open-space) — your own open space data
- [`sampling`](#sampling-configuration) — where and how sample points are generated

For custom areas to summarise results for, see [Custom aggregation](https://healthysustainablecities.github.io/global-indicators/Custom-aggregation) instead.

## Custom points of interest

Destinations are grouped into categories, identified by a short name (`dest_name`).  The categories analysed by default are:

| `dest_name` | Indicator |
|---|---|
| `fresh_food_market` | Access to a supermarket or fresh food market within 500 m |
| `convenience` | Access to a convenience store within 500 m |
| `pt_any` | Access to a public transport stop within 500 m |

Data for any of these may be supplied under `points_of_interest`, keyed by the category name:

```yaml
points_of_interest:
  fresh_food_market:
    data: other_custom_data/my_supermarkets.geojson
    replace: true
    source: City of Example open data portal
    publication_date: 2024
    licence: CC BY 4.0
    url: https://data.example.gov/supermarkets
```

The data are loaded with `ogr2ogr` and reprojected to the study region's coordinate reference system automatically.  Point centroids are recorded as destinations, so polygon data (building footprints, land parcels) may be supplied as well as points.

### Supplementing or replacing OpenStreetMap

- **`replace: true`** — the OpenStreetMap import for that category is skipped entirely, and your data provide all of its destinations.
- **`replace: false`** (the default) — your features are pooled with those identified from OpenStreetMap.

Pooling is sound for the analyses undertaken here, which measure distance to the *closest* destination of each category: a destination appearing in both datasets does not change the distance to the closest one.  It does mean the reported *count* of destinations in a category will double count anything present in both, so use `replace: true` if you want counts to be exact, or if you consider your data more complete than OpenStreetMap for that category.

### Selecting a layer, or filtering features

As elsewhere in the configuration, a layer within a geopackage may be selected by appending its name after a colon, and features may be filtered with an OGR `-where` clause:

```yaml
data: "other_custom_data/my_data.gpkg:retail -where \"CATEGORY='supermarket'\""
```

The `-where` clause may also be used on its own with other formats:

```yaml
data: "other_custom_data/my_retail.shp -where \"CATEGORY='supermarket'\""
```

### Other destination categories

`configuration/osm_destination_definitions.csv` defines further categories that are imported and mapped but not analysed by default, including `restaurant`, `cafe`, `food_court`, `fast_food`, `pub` and `bar`.  Data may be supplied for these in the same way.

You may also define a category of your own.  Because it cannot be looked up, give it a plain language name and a domain:

```yaml
points_of_interest:
  community_centre:
    data: other_custom_data/my_community_centres.geojson
    dest_name_full: Community centre
    domain: Community facilities
```

**A new category will not produce an access indicator on its own.**  It will be imported, counted and included in the study region geopackage, but an indicator is only calculated for categories listed under `Destinations` in `configuration/indicators.yml`.  To have one calculated, that file must also be extended to include the new category and its output name.  This is the most common surprise when supplying custom destinations, so it is worth checking your indicator output before running a full analysis.

### A note on naming

The project level configuration file, `configuration/config.yml`, also has a `points_of_interest` setting.  That one records the OpenStreetMap destination definitions used across all study regions, and is unrelated to the region level setting described here.

### Deprecated: `custom_destinations`

Older configurations may use a `custom_destinations` section, describing a single file of points with `name_field`, `description_field`, `lat`, `lon` and `epsg` parameters.  This is retained so that existing configurations continue to work, but it is not recommended for new ones: use `points_of_interest` instead, which handles any spatial format and coordinate reference system, supports layer selection and filtering, and can replace as well as supplement OpenStreetMap.

## Custom public open space

Areas of public open space are otherwise derived from OpenStreetMap using the tag definitions in `configuration/osm_open_space.yml` — a substantial piece of processing that identifies open space, works out which parts of it are publicly accessible, and locates entry points near the pedestrian network.

Supplying `public_open_space` **replaces** that process:

```yaml
public_open_space:
  data: "other_custom_data/my_open_space.gpkg:parks"
  source: City of Example open data portal
  publication_date: 2024
  licence: CC BY 4.0
  url: https://data.example.gov/open-space
```

The supplied polygons are taken to be the public open space of the study region in their entirety.  Two things follow:

- **The data must already be restricted to publicly accessible areas.** No further filtering for public access is applied.  Golf courses, school grounds, private gardens and defence land should be excluded beforehand if they are not publicly accessible in your city.
- **The polygon areas are used directly.** Each feature's area determines whether it counts towards the 'any' open space indicator, or the 'large' indicator for spaces over 1.5 hectares.

Entry points are then derived along the boundaries of the supplied features, and access is measured to those within 30 metres of the pedestrian network, exactly as for the OpenStreetMap derived open space.

A layer may be selected and features filtered as described above, which is often how the public subset is chosen:

```yaml
data: "other_custom_data/my_open_space.gpkg:open_space -where \"ACCESS='public'\""
```

If the configured data cannot be read, or if it is read but no features fall within the study region, the analysis stops with an error explaining what to check.  This is deliberate: an empty open space layer would otherwise be carried silently through to the indicators, reporting the city as having no public open space at all.

## Sampling configuration

Sample points are generated along the pedestrian network at a regular interval, wherever there is population data coverage.  Areas with no population estimate — a new development post-dating a census, say — are not sampled by default, and so have no indicator estimates at all.

The `sampling` section changes this:

```yaml
sampling:
  sample_unpopulated_areas: true
  custom_sample_points: other_custom_data/my_addresses.geojson
  custom_sample_points_snap_tolerance: 500
```

### `sample_unpopulated_areas`

Set to `true` to sample the full urban study region regardless of population data coverage.  Alternatively, give the path to a polygon layer to restrict the additional sampling to specific areas of interest.

Sample points that lack population data coverage are **excluded from population weighted grid and city summaries** — they cannot be weighted, having no population — but they **are included in custom aggregations**.  This is what makes the option useful: indicator estimates can be produced for a new development and reported through a custom aggregation, without disturbing the city level statistics.

### `custom_sample_points`

The path to a point layer of locations to be analysed in addition to those generated along the network — address points, dwelling centroids, or specific sites of interest.  Each point is associated with the nearest network edge within the snap tolerance.

### `custom_sample_points_snap_tolerance`

The maximum distance in metres from the network within which a custom sample point will be associated with its nearest edge.  Defaults to 500.  Points further than this from any pedestrian network edge are not analysed.

## See also

- [Custom aggregation](https://healthysustainablecities.github.io/global-indicators/Custom-aggregation) — summarising results for your own areas
- [Data](https://healthysustainablecities.github.io/global-indicators/6.-Data) — sourcing and storing input data
- [Advanced features](https://healthysustainablecities.github.io/global-indicators/7.-Advanced-Features)
