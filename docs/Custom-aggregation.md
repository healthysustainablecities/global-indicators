---
layout: default
title: Custom aggregation
permalink: /Custom-aggregation/
---

# Custom aggregation

Indicators are calculated by default for three scales: sample points along the pedestrian network, the population grid, and the study region overall.  Custom aggregation lets you add a fourth: any set of areas you care about — administrative boundaries, statistical areas, school catchments, neighbourhoods, a planned development, or even individual buildings.

This is configured under `custom_aggregations` in your study region configuration file.  It is one of the more powerful parts of the configuration, and one of the least obvious, so this page explains what each option does and why you might want it.

## How it works

Each entry under `custom_aggregations` names an aggregation, and describes the areas to summarise for and the results to summarise from:

```yaml
custom_aggregations:
  my_aggregation_name:
    data: region_boundaries/my_areas.geojson
    id: AREA_CODE
    keep_columns: AREA_NAME
    aggregation_source: grid
    weight: pop_est
    note: "A description of what this aggregation represents."
```

The boundaries are loaded into the study region database, the configured indicator results are summarised for each one, and a table named `indicators_<my_aggregation_name>` is produced.  This is exported as a CSV and as a layer in the study region geopackage when you run `generate`.

**Aggregations are processed in the order they appear in your configuration file.**  This matters because an aggregation may be summarised from an earlier one (see [chaining](#chaining-aggregations) below).  A source that has not yet been processed cannot be found, and that aggregation is skipped with a message rather than failing the analysis — so if an expected output is missing, check the ordering first.

Areas containing no features from the aggregation source are removed from the output table, because no estimate can be made for them.  An aggregation of areas that extend beyond the study region will therefore return fewer areas than you supplied.

## Configuration options

### `data` — the areas to aggregate for

A path to a spatial data file, relative to the `process/data` folder.  Any format readable by GDAL/OGR will work (geojson, shapefile, geopackage).  The data are reprojected to the study region's coordinate reference system automatically.

To use a specific layer within a geopackage, append the layer name after a colon:

```yaml
data: "region_boundaries/my_geopackage.gpkg:suburbs"
```

Features may then also be filtered with an OGR `-where` clause:

```yaml
data: "region_boundaries/my_geopackage.gpkg:suburbs -where \"STATE='Victoria'\""
```

Note that for custom aggregations the `-where` clause must follow a `layer_name` selection like this; it is not supported on its own for other formats.

Alternatively, areas may be selected from the OpenStreetMap data already imported for the study region, using the `OSM:` prefix followed by a condition on the OpenStreetMap polygons:

```yaml
data: "OSM:building is not NULL"
```

### `id` — the unique identifier

The field that uniquely identifies each area, used as the primary identifier in the output.  Defaults to `ogc_fid`, the sequential identifier assigned on import.  Where the source data has a meaningful code (a census area code, an administrative identifier), name it here so that results can be joined to other data.

Column names are lower cased on import, so an `id` of `AREA_CODE` appears in the output as `area_code`.

### `keep_columns` — additional attributes to retain

A comma separated list of fields from the boundary data to carry through to the output, for example a place name.  Anything not listed here is discarded.

Columns retained here are also available as weights if this aggregation is later used as the source for another one, which is what makes chaining useful.

### `aggregation_source` — the results to summarise

One of:

- **`point`** — the sample point estimates taken along the pedestrian network.  Use this for areas smaller than the population grid, or for features unlikely to intersect the grid meaningfully (buildings, addresses).
- **`grid`** — the population grid indicator results.  Use this for areas comparable to or larger than the grid cells, where population weighting is wanted.
- **the name of an earlier aggregation** — see [chaining](#chaining-aggregations).

### `weight` — the variable used for weighting

This is the option most worth understanding, because it behaves differently depending on the aggregation source.

**Where the source is areal** — the population grid, or an earlier aggregation — the named column is looked for in that source.  Its values are summed across the units falling within each area to give that area's total, reported as `pop_est`, and the indicator estimates are weighted by it.  Setting `weight: pop_est` with `aggregation_source: grid` gives population weighted indicator estimates, which is usually what you want when summarising to administrative areas.

**Where the source is sample points**, the weight is instead read from the aggregation boundaries themselves.  Sample points are equal probability samples of the pedestrian network, so summing a boundary attribute once per point would multiply it by the number of points that happened to fall in that area.  Instead, the boundary's own value is reported as its population estimate, and the indicator estimates remain unweighted averages of the points within it.  Weighting them would have no effect in any case, since a boundary attribute is constant within the boundary.

Names are matched **case insensitively**, because column names are lower cased when data are imported.  A configuration saying `weight: POBTOT` will match an imported `pobtot`.

**A numeric value** (e.g. `weight: 3.2`) assigns that constant as `pop_est` for every output row — useful when the boundary data carries no population field and a fixed per-feature assumption is appropriate.  Indicator estimates remain unweighted (a constant weight cancels in a weighted average).  `pop_per_sqkm` is still derived as `pop_est / area_sqkm`, so it varies across rows.  Downstream aggregations can then propagate these estimates by naming this layer as their `aggregation_source` and setting `weight: pop_est`.

Leave `weight` blank, or set it to `false`, for no weighting; `pop_est` is then reported as null.

A weight that cannot be found in either the source or the boundaries produces a warning naming the tables that were searched, and the aggregation proceeds unweighted.  It does not halt the analysis — so if `pop_est` is unexpectedly empty, check the processing log for that warning.

### `area_weighted` — apportioning units that straddle a boundary

Defaults to `true`.  Grid cells that straddle an aggregation boundary are apportioned by the share of their area falling within it, so that a cell's population is divided between the areas it spans rather than counted in full in each.  Without this, populations summed across adjoining areas would exceed the region total.

This rests on an assumption worth stating: that the weight is distributed evenly within each unit.  For a coastal area, or one bounded by an airport, a reserve or an industrial estate, the populated part of a straddling cell may lie entirely on one side of the boundary, and apportionment by area will then understate one side and overstate the other.  Set `area_weighted: false` to instead attribute the full weight of every intersecting cell to each area it touches, if that better suits your data.

Apportionment applies only where the source is areal, a weight is defined, and `aggregate_within_distance` is not used.

### `aggregate_within_distance` — summarising a catchment

A distance in metres.  Instead of summarising the units that intersect each area, those within this distance of it are summarised.

This is how the buildings example below works: sample points are taken along the pedestrian network, so they rarely fall inside a building footprint.  Taking the average of points within 30 metres gives something like a moving window average, representing the immediate neighbourhood milieu around each building.

Two consequences follow from the fact that such catchments **may overlap one another, and need not intersect the units they summarise**:

- area apportionment does not apply, and is ignored if configured;
- the reported `intersection_count` is per catchment, so summing it across aggregation units can legitimately exceed the study region total.  The same intersection is counted for every catchment that reaches it.  This looks like an error, and is not.

### `note`

Free text describing what this aggregation represents and where the boundary data came from.  It is carried into the generated metadata, so it is worth writing properly — including the source, licence and currency of the boundary data.

## What is produced

For each aggregation, a table `indicators_<name>` with:

| Column | Description |
|---|---|
| the configured `id` | unique identifier for the area |
| any `keep_columns` | retained attributes |
| `area_sqkm` | area in square kilometres |
| `pop_est` | the summed (or boundary) weight; null if unweighted |
| `pop_per_sqkm` | `pop_est` divided by `area_sqkm` |
| `intersection_count` | intersections within (or within the catchment of) the area |
| `intersections_per_sqkm` | intersection density |
| `grid_count` / `urban_sample_point_count` / `area_count` | how many source units were summarised, named for the kind of source |
| indicator estimates | one column per indicator |
| `geom` | the area geometry |

Where a weight is applied, the indicator columns are prefixed with the weight variable, for example `pop_est_pct_access_500m_fresh_food_market_score`.  Where estimates are unweighted, the plain indicator name is used, for example `pct_access_500m_fresh_food_market_score`.  This distinction is deliberate: it keeps weighted and unweighted estimates from being mistaken for one another.

## Worked examples

### 1. Population weighted aggregation to school catchment districts

This example ships with the example study region, and summarises the population grid results for high school catchment districts in Las Palmas de Gran Canaria:

```yaml
custom_aggregations:
  school_districts_grid_pop:
    data: "region_boundaries/Example/Las Palmas excerpt- gobcan_educacion_areainfluenciacentrosecundaria.geojson"
    id: 'Codigo'
    keep_columns: Denominaci, cod_postal
    aggregation_source: grid
    weight: pop_est
    note: "Example of aggregating indicators for high school catchment districts within Las Palmas, using the intersection with the population grid and taking the population weighted average of indicators, apportioned by the share of each grid cell's area within the district."
```

The output has one row per district, with columns including `codigo`, `denominaci`, `cod_postal`, `area_sqkm`, `pop_est`, `grid_count`, and population weighted estimates such as `pop_est_pct_access_500m_convenience_score` and `pop_est_local_walkability`.

Because the catchment districts do not cover the whole urban study region, their apportioned populations sum to less than the region total — around 306,500 of the region's 331,400 in this example.  That is expected, and is a useful check that apportionment is behaving: without it, the sum would exceed the region total instead.

### 2. Unweighted aggregation to buildings, using a catchment

Also shipped with the example region:

```yaml
  buildings_osm_30m:
    data: "OSM:building is not NULL"
    keep_columns: building
    aggregate_within_distance: 30
    aggregation_source: point
    note: "Example of aggregating using buildings extracted from the configured OpenStreetMap data, taking the average of sample point estimates taken along the pedestrian network within 30m."
```

Here the areas are the building footprints in the OpenStreetMap extract for the study region — around 21,000 of them appear in the output.  No weight is configured, so `pop_est` is null and the indicator estimates are plain averages of the sample points within 30 metres of each building: `pct_access_500m_convenience_score`, `local_walkability`, and so on.  Buildings with no sample point within 30 metres are dropped from the output, so the output has fewer rows than there are buildings in the data.

### 3. Chaining aggregations

`aggregation_source` may name another aggregation, allowing results to be rolled up through a hierarchy of areas.  This is useful where official small area statistics are available: sample point estimates are first averaged for the smallest available unit, and those results are then aggregated upwards weighted by a population or dwelling count.

Because the source must already have been processed, **it must be defined before the aggregation that uses it**:

```yaml
custom_aggregations:
  mesh_blocks:
    data: "region_boundaries/your_mesh_blocks.gpkg:mesh_blocks"
    id: 'MB_CODE'
    keep_columns: SUBURB_NAME, DWELLINGS
    aggregation_source: point
    weight: DWELLINGS
    note: "Sample point indicator estimates averaged for mesh blocks, the smallest available area unit."
  suburbs:
    data: "region_boundaries/your_suburbs.gpkg:suburbs"
    id: 'SUBURB_CODE'
    keep_columns: SUBURB_NAME
    aggregation_source: mesh_blocks
    weight: DWELLINGS
    note: "Mesh block indicator estimates aggregated for suburbs, weighted by the number of dwellings in each mesh block."
```

Note how `weight: DWELLINGS` means two different things in the two entries, exactly as described under [`weight`](#weight--the-variable-used-for-weighting) above:

- for `mesh_blocks`, the source is sample points, so `DWELLINGS` is read from the mesh block boundaries.  It is reported as each mesh block's `pop_est`, and the indicator estimates are unweighted averages of the points within the block.
- for `suburbs`, the source is the `mesh_blocks` aggregation, which is areal.  `DWELLINGS` was retained there using `keep_columns`, so it is summed for each suburb and the mesh block estimates are weighted by it.

Retaining the weight column with `keep_columns` at each level is what makes the chain work.  Without it, the weight would not be found in the source at the next level up, and that level would fall back to unweighted estimates with a warning.

## Using an aggregation as the population denominator

By default, city level summaries are population weighted using the population grid.  Where official small area population statistics are available and considered more meaningful for your audience, a custom aggregation may be used instead:

```yaml
population:
  ## ... other population configuration ...
  custom_population: suburbs
```

The named aggregation must be defined under `custom_aggregations` and be weighted by a population variable.  City summaries are then calculated from `indicators_suburbs` rather than from the population grid.

## Things to watch for

- **Ordering.** A chained `aggregation_source` must be defined earlier in the file.
- **Missing output.** An aggregation whose source could not be identified is skipped with a message; check the processing log at `process/data/_study_region_outputs/<codename>/__<name>__<codename>_processing_log.txt`.
- **Empty `pop_est`.** Either no weight was configured, or the configured weight was not found; the log will say which tables were searched.
- **Fewer areas than expected.** Areas containing no source features are removed.
- **`intersection_count` summing to more than the region total.** Expected when `aggregate_within_distance` is used, because catchments overlap.
- **Populations that look low at the edges.** Area apportionment assumes an even distribution of population within each grid cell; see [`area_weighted`](#area_weighted--apportioning-units-that-straddle-a-boundary).

## See also

- [Custom data](https://healthysustainablecities.github.io/global-indicators/Custom-data) — supplying your own destinations, public open space, and sample points
- [Data](https://healthysustainablecities.github.io/global-indicators/6.-Data) — sourcing and storing input data
- [Advanced features](https://healthysustainablecities.github.io/global-indicators/7.-Advanced-Features)
