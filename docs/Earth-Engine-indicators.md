---
layout: default
title: Earth Engine indicators
permalink: /Earth-Engine-indicators/
---

# Earth Engine indicators

Two optional spatial indicators are generated using [Google Earth Engine](https://earthengine.google.com/), a cloud-based platform for planetary-scale geospatial analysis:

1. **Large Public Urban Green Space (LPUGS)** — availability of, and access to, large public urban green space.
2. **Global Urban Heat Vulnerability Index (GUHVI)** — a composite index of urban heat vulnerability, along with the sub-indices and sub-indicators that make it up.

These are optional.  With `gee: false`, or when running the standard container, they are simply skipped and the software behaves exactly as it otherwise would.

Earth Engine is free for noncommercial and research use, as detailed on the [Earth Engine noncommercial page](https://earthengine.google.com/noncommercial/).

## What is required

To generate these indicators you need three things:

1. **A Google Cloud project registered for Earth Engine.** This is a one-off setup involving creating a project, enabling the Earth Engine API, and registering it for commercial or non-commercial use.
2. **The Earth Engine container.** These indicators use a separate container image to the standard one, launched with `.\global-indicators-ee.bat` on Windows, or `bash ./global-indicators-ee.sh` on MacOS and Linux.  You will be prompted for your Cloud Project ID and taken through a sign-in flow the first time; the credentials are saved and reused thereafter.
3. **`gee: true` in your study region configuration file.**

Full step-by-step directions for the first two — creating the Cloud project, enabling the API, registering, launching the container, authenticating, and viewing or removing saved credentials — are maintained in the software [readme](https://github.com/healthysustainablecities/global-indicators#optional-indicators-using-google-earth-engine).  They are kept there rather than duplicated here so that there is a single, current set of instructions to follow.

## Configuring a study region

Set `gee` in your study region configuration file:

```yaml
## Optional Google Earth Engine indicator configuration
## Set 'gee' below to true to compute and generate the below indicators, or set false to skip
## 1. Large Public Urban Green Space (LPUGS) accessibility and availability
## 2. Global Urban Heat Vulnerability Index (GUHVI)
gee: true
```

To include the results in generated reports, use the Earth Engine report templates:

```yaml
reporting:
  templates:
    - spatial_ee
    - policy_spatial_ee
```

These are the equivalents of the standard `spatial` and `policy_spatial` templates, with the additional indicators included.  The `policy_spatial_ee` template, like `policy_spatial`, also requires a completed policy review checklist.

A fully worked example configuration is provided as `process/data/examples/ES_Las_Palmas_2025/configuration/ES_Las_Palmas_2025-ee.yml` (load it with `ghsci.example('ee')`).  It is identical to the standard example region configuration apart from `gee: true` and the two `_ee` report templates, so comparing the two shows exactly what enabling Earth Engine involves.

## If Earth Engine is not available

Configuration is checked when a study region is loaded.  If `gee: true` but Earth Engine cannot be initialised — because the standard container was launched rather than the Earth Engine one, or because authentication has not been completed — a message is displayed explaining that the optional Earth Engine indicator processing will be skipped, and the analysis proceeds without those indicators.

This means a configuration with `gee: true` remains usable by collaborators who have not set up a Cloud project.  They will simply produce the core indicator set.  Note that the `spatial_ee` and `policy_spatial_ee` report templates expect the Earth Engine indicators, so use the standard `spatial` and `policy_spatial` templates in that case.

## The indicators

### Large Public Urban Green Space

Large public urban green space is identified from satellite imagery, and access to it is measured along the pedestrian network in the same way as for other destinations, producing:

- `pct_access_500m_large_public_green_space_score` at the grid scale, and the corresponding population weighted city estimate `pop_pct_access_500m_large_public_green_space_score`
- a `large_public_urban_green_space` layer in the study region geopackage, which is used as a map overlay in the generated report

### Global Urban Heat Vulnerability Index

The GUHVI is the equal weighted average of three sub-indices, each derived in turn from normalised sub-indicators:

| Sub-index | Sub-indicators |
|---|---|
| Heat Exposure Index (HEI) | land surface temperature |
| Heat Sensitivity Index (HSI) | land surface albedo, NDVI, NDBI, local climate zone, population density, vulnerable population percentage |
| Adaptive Capability Index (ACI) | child dependency ratio, subnational Human Development Index, infant mortality rate |

These combine into the overall `urban_heat_guhvi`.  It is also reported as a five-class categorisation, `urban_heat_guhvi_class`, cut at the 20th, 40th, 60th and 80th percentiles of the study region, and as the percentage of the population in the most vulnerable class, `pop_pct_urban_heat_guhvi_class_5_most_vulnerable`.  Because the classes are percentile based, they describe relative vulnerability *within* a city and are not comparable between cities; the underlying `urban_heat_guhvi` values are.

Each sub-index and sub-indicator is reported alongside the overall index, at the sample point, grid and city scales, following the same naming conventions as the core indicators: `sp_` prefixed at sample points, unprefixed at the grid scale, and `pop_` prefixed for population weighted city estimates.

The methods follow Turner et al. (2025), *Urban Climate* 64:102716.  Note that the urban heat indicators are estimated on a 1 km grid, which is coarser than the population grid typically used for the core indicators.

The full list of variable names is in `configuration/indicators-ee.yml`, and descriptions of the green space indicators are in the reference data dictionary at `configuration/assets/output_data_dictionary.csv`.

## Where the definitions live

When Earth Engine is enabled and available, indicator definitions are read from `configuration/indicators-ee.yml` instead of `configuration/indicators.yml`.  The file is refreshed from its template when it differs, so that the indicator definitions stay current with the software version.

## See also

- [Running the software](https://healthysustainablecities.github.io/global-indicators/3.-Running-the-Software)
- [Analysis and generate resources](https://healthysustainablecities.github.io/global-indicators/4.-Analysis-&-Generate-Resources)
- [Indicators](https://healthysustainablecities.github.io/global-indicators/Indicators)
