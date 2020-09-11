# Indicators Analysis

This folder contains notebooks to generate visualizations and calculate descriptive stats of the global livability indicators calculated in the process folder. These analyses include within-city and between-city analyses.

## Instructions

To run the notebooks:

  1. Download all the indicators data output GeoPackages from [Cloudstor](https://cloudstor.aarnet.edu.au/plus/s/nYtHf1UqN9AAZX1). These include:  
    - Hex-level output: global_indicators_hex_250m.gpkg.   
    - City-level output: global_indicators_city.gpkg.   
    - City-specific output: studyregion_country_yyyy_1600m_outputyyyymmdd.gpkg (e.g. phoenix_us_2020_1600m_buffer_output20200820.gpkg).   
  2. Place the hex- and city-level indicators output data in the process/data/output folder, and the city-specific output in the process/data/input folder
  3. Run the notebooks.

## Development Guidelines

### Image/Mapping Guidelines

  - Generated figures should not exceed 8-inches in their largest dimension or 600 DPI when saving
  - Maps should have a black background, title, and scalebar
  - Maps should use the plasma colormap
  - Maps' data should range from "worst" values (eg, low walkability) in a dark color to "best" values in a light color (eg, high walkability)

### Commit Guidelines

  - Make sure no images appear inline in notebooks.
  - Do not commit any image files.
