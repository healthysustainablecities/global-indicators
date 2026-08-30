---
layout: default
title: Custom data
permalink: /Custom-data/
---

# Custom data

By default, the software identifies destinations and public open space from OpenStreetMap, and generates sample points along the pedestrian network wherever there is population data coverage.  Each of these can be supplemented or replaced with your own data, which may be preferable where an authoritative local dataset exists, or where OpenStreetMap coverage of your city is incomplete.

This page covers three optional sections of the study region configuration file:

- [`points_of_interest`](#custom-points-of-interest) — your own destination data
- [`areas_of_interest`](#custom-areas-of-interest) — your own open space and blue space data, and region-specific OpenStreetMap open space definitions
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

### More than one dataset for a category

Where a category is assembled from several sources — a supermarket dataset and a fresh food market dataset, say — list them under `data_sources`, with `replace` set once for the category as a whole:

```yaml
points_of_interest:
  fresh_food_market:
    replace: true
    data_sources:
      - data: other_custom_data/my_supermarkets.geojson
        source: City of Example open data portal
        publication_date: 2024
        licence: CC BY 4.0
      - data: other_custom_data/my_markets.geojson
        source: Regional government market register
        publication_date: 2023
        licence: CC BY 4.0
```

`replace` relates to the category, not to an individual dataset: it determines whether the pooled custom data replace the OpenStreetMap derivation for that category.  Custom datasets never replace one another — they are always pooled with each other.  Setting `replace` on an individual entry so that it contradicts the category-level setting is reported as an error rather than silently resolved.

A bare list of entries is also accepted, in which case any per-entry `replace` settings must agree.

Destinations are restricted to the buffered urban study region on import, and the tags carried by each feature are recorded, so that categories can be queried and refined after the fact.

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

You may also define a category of your own, along with a plain language name and domain:

```yaml
points_of_interest:
  community_centre:
    data: other_custom_data/my_community_centres.geojson
    dest_name_full: Community centre
    domain: Community facilities
```

**A new category will not currently produce an access indicator on its own.**  It will be imported, counted and included in the study region geopackage, but an indicator is only calculated for categories listed under `Destinations` in `configuration/indicators.yml`.  To have one calculated, that file must also be extended to include the new category and its output name.  

An update has been planned that allows for configuring new indicators directly in configuration files.

#### Note

The project level configuration file, `configuration/config.yml`, also has a `points_of_interest` setting.  That one records the OpenStreetMap destination definitions used across all study regions, and is unrelated to the region level setting described here.

#### Deprecated: `custom_destinations`

Older configurations may use a `custom_destinations` section, describing a single file of points with `name_field`, `description_field`, `lat`, `lon` and `epsg` parameters.  This is retained so that existing configurations continue to work, but it is not recommended for new ones: use `points_of_interest` instead, which handles any spatial format and coordinate reference system, supports layer selection and filtering, and can replace as well as supplement OpenStreetMap.

## Custom areas of interest

Areas of public open space are otherwise derived from OpenStreetMap using the tag definitions in `configuration/osm_open_space.yml` — a substantial piece of processing that identifies open space, works out which parts of it are publicly accessible, and locates entry points near the pedestrian network.

The `areas_of_interest` section provides four ways to adapt this to your city:

| Setting | Purpose |
|---|---|
| `public_open_space` | Your own open space data, supplementing or replacing that derived from OpenStreetMap |
| `blue_space` | Your own rivers, canals, lakes and coastline, supplementing that derived from OpenStreetMap |
| `public_open_space_variants` | Which open space node layers are derived, and on what criteria |
| `osm_open_space` | Region-specific overrides of the OpenStreetMap open space tag definitions |

### `public_open_space`

Your own open space data may supplement or replace that derived from OpenStreetMap:

```yaml
areas_of_interest:
  public_open_space:
    replace: true
    data_sources:
      - data: "other_custom_data/my_open_space.gpkg:parks"
        source: City of Example open data portal
        publication_date: 2024
        licence: CC BY 4.0
        url: https://data.example.gov/open-space
```

As for destinations, `replace` relates to the category as a whole, and a single data entry or a bare list may be given instead of the `data_sources` form.  A legacy top-level `public_open_space` section is also still read, and implies `replace: true`.

**You do not need to filter your data by size.**  The software measures each supplied polygon and applies the size threshold itself: every area contributes to the 'any' open space indicator, and those over 1.5 hectares additionally contribute to the 'large' one.  The threshold is defined by the `large` entry of [`public_open_space_variants`](#public_open_space_variants), and can be changed there.

**You do need to filter your data for public access.**  The supplied polygons are taken to be publicly accessible in their entirety, and no further filtering is applied.  Golf courses, school grounds, private gardens and defence land should be excluded beforehand if they are not publicly accessible in your city.

Entry points are then derived along the boundaries of the supplied features, and access is measured to those within 30 metres of the pedestrian network, exactly as for the OpenStreetMap derived open space.  Features are restricted to those intersecting the buffered urban study region.

A layer may be selected and features filtered as described above, which is often how the public subset is chosen:

```yaml
data: "other_custom_data/my_open_space.gpkg:open_space -where \"ACCESS='public'\""
```

If the configured data cannot be read, or if it is read but no features fall within the study region, the analysis stops with an error explaining what to check.  This is deliberate: an empty open space layer would otherwise be carried silently through to the indicators, reporting the city as having no public open space at all.

### `blue_space`

Rivers, canals, lakes, reservoirs and coastline are otherwise identified from OpenStreetMap.  Where a local authority maps your city's water network more completely, supply it here:

```yaml
areas_of_interest:
  blue_space:
    data: "other_custom_data/my_waterways.gpkg:water"
    source: National hydrography dataset
    publication_date: 2024
    licence: CC BY 4.0
```

Custom blue space is appended to the OpenStreetMap derived layer rather than replacing it, and re-running the analysis replaces what a previous run appended rather than duplicating it.  Polygons are sampled along their exterior ring and linear features along their length, so that walking access to a lake shore or a canal bank is measured exactly as access to any other destination is.

Blue space also attributes the open space areas near it: `aos_ha_water` records the water within an area, and `aos_blue_distance_m` the distance from it to the nearest blue space.  Both are available in the study region database and to [`public_open_space_variants`](#public_open_space_variants).

> **Blue space does not produce an access indicator of its own.**  The layers are built, and the attributes above are recorded, but no blue space indicator is calculated: the indicators derived from open space are those listed under `Destinations` in `configuration/indicators.yml`, and the set of layers analysed in `_11_neighbourhood_analysis.py` is fixed.  Calculating one would require extending both.  This is the same limitation as applies to a new destination category, described above.

### `public_open_space_variants`

By default, three sets of open space access points are derived: `any` (all public open space), `large` (over 1.5 hectares), and `water` (open space containing water).  A region may redefine these, or add its own, by giving an SQL condition on the public open space table:

```yaml
areas_of_interest:
  public_open_space_variants:
    large: a.aos_ha_public > 2
    waterfront: a.aos_blue_distance_m < 50
```

`aos_blue_distance_m` is available here, so water-adjacent open space can be defined without altering what counts as public open space.

Each variant produces a layer of access points named `aos_public_<name>_nodes_30m_line`, which you can inspect in the study region geopackage or database.

> **Only the `any` and `large` variants produce indicators.**  A variant you add, and the built-in `water` variant, build their access point layers but are not carried through to indicator estimates, for the same reason as blue space above.  Changing the `large` threshold does change the `public_open_space_large` indicator, because that variant is already analysed.

### `osm_open_space`

Which OpenStreetMap features count as open space is defined globally in `configuration/osm_open_space.yml`.  Where a locally relevant typology is missed by those definitions, individual definitions can be overridden for one region, without pre-processing custom data.  The intended workflow is to copy the relevant `criteria` from the global configuration and edit it — here, to count urban forests as public open space:

```yaml
areas_of_interest:
  osm_open_space:
    os_inclusion: "p.leisure IS NOT NULL OR ... OR p.\"natural\" IN ('wood')"
```

The value may be given directly as the replacement criteria (a string, or a list for list-valued definitions such as `os_required`), or as a mapping containing a `criteria` key, so that a whole block may be copied from the global configuration and edited in place.  An unrecognised definition name is reported as an error, listing the valid ones.

Any definition not listed keeps its global default; a definition that is listed has its criteria replaced outright.  Overrides are applied to a copy, so they never leak into other regions analysed in the same session.

Note that overriding a definition opts that region out of subsequent improvements to the global default, and that its results are not directly comparable with regions using the defaults — record any override in the region's validation provenance.  The derived criteria (`public_space`, `exclusion_criteria`) are always recomposed from their source definitions, and so cannot be overridden directly.

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
