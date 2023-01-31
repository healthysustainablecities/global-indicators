---
title: Global Healthy and Sustainable City Indicators
layout: collection
permalink: /faq/
collection: faq
entries_layout: grid
classes: wide
---
*2023 draft in progress*

## Assumed knowledge
- Basic familiarity with Docker, Git, YAML, some Python
- Awareness of fundamental geographical and network analysis concepts useful
- Not assumed, but useful
    - Familiarity with OpenStreetMap and its key:value pair tagging system for classifying data
    - Familiarity with QGIS (or other GIS software) useful for mapping
    - Postgresql and Postgis useful for more advanced data management and querying
    
## Software installation
- Git
- Docker
- Platform-specific considerations?

## Create and customise project configuration files
- Project
- Regions
- Datasets
    - required:
      - OpenStreetMap
      - Population grid (Global Human Settlements Layer r2022a or later recommended)
    - optional
      - Urban region 
        - Global Human Settlements Layer Urban Centres Database recommended)
          - this also contains additional covariates for urban areas that may be optionally linked
      - GTFS (transport schedule data)
- Indicators
- Policies
  - a checklist of policies for reporting purposes
  
## Set up study region resources
- Incorporates the following automated processes:
  - Create database for region
  - Create study region boundaries
    - boundary for region of interest (ie. urban and/or policy relevant administrative extent; pending configuration)
    - buffered boundary for data retrieval and analysis to mitigate risk of edge effects
  - Extract OpenStreetMap feature data for region
  - Derive routable pedestrian network and intersections data
  - Set up grid with population estimates for region
  - Compile destinations using OpenStreetMap and/or custom data
  - Derive a dataset of areas of open space
     - Currently focused on 'public open space'
     - It is planned to broaden this to include more flexibility in analysis (green space, blue space, etc)
  - Pre-compute distance relationships for nodes and destinations to facilitate subsequent network analysis
  - Summarise destinations
  - Link urban covariates
  - Analyse service frequency for public transport stops (optional; using GTFS data)
  
## Analyse neighbourhood indicators for sample points
- Access to amenities (food market, convenience store, open space typologies, public transport typologies)
- Daily Living score for access to amenities
- Walkability index
   - within city
        - A walkability index is calculated as a sum of standard scores (z-scores) for population density, street connectivity and daily living score for access to amenities
   - between cities
        - In addition to the within-city walkability index, a reference walkability index is also calculated.  Using the default configuration this draw upon 25-city study results to make comparisons using sub-indicator mean and standard deviation to calculate z-scores, which are then summed.
   
## Aggregate point estimates
- grid area estimates
- overall city summary estimates
    - distinction between spatial and population-weighted estimates 
    
## Generate reports
- Policy and spatial indicator summary report
  - optionally configure for multiple languages
  - currently PDF designed for web distribution (as per 25 city study; same basic design)
  - templates planned for print, and optionally select policy and/or spatial indicators for reporting
- Planned to incorporate validation reporting with descriptive and analytical summaries
  - currently, validation is to be carried out by users independent of the process
  - previous validation code (reporting and quantitative analysis) requires updating for new process/software
