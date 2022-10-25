# global-indicators

An open-source tool for estimation of spatial indicators for healthy, sustainable cities worldwide using open data such as OpenStreetMap, the Global Human Settlement Layer (GHSL), and GTFS feeds (where available).

This Python-based tool presents a generalized method to measure pedestrian accessibility indicators within- and between-city at both city scale and high-resolution grid level. The methodology and the open data approach developed in this research can be expanded to many cities worldwide to support local policy making towards healthy and sustainable living environments.

The process scripts enable computation of the following indicators of pedestrian accessibility:
1. Urban area in square kilometers
2. Population size and population density  
3. Street connectivity: intersections per square kilometer
4. Access to destinations: population access within 500 meters walking distance to:  
    - a supermarkets
    - a convenience store
    - any public open space (e.g. parks)
    - any public transport stop (any mode)
5. Daily living score
6. Walkability index

## Documentation and Citation
Please refer to the documentation folder readme for more information about this repository.

Usage of our tool may be cited through reference of the following paper, which provides further detail on the methods used: 

Liu, S., Higgs, C., Arundel, J., Boeing, G., Cerdera, N., Moctezuma, D., Cerin, E., Adlakha, D., Lowe, M. and Giles-Corti, B. (2021), A Generalized Framework for Measuring Pedestrian Accessibility around the World Using Open Data. Geogr Anal. https://doi.org/10.1111/gean.12290

# How to set up and get started?

1. Install [Git](https://git-scm.com/downloads) and [Docker](https://www.docker.com/products/docker-desktop)
2. Git clone https://github.com/global-healthy-liveable-cities/global-indicators.git, or fork the repo and then git clone a local copy to your machine. For help on this, please refer to the [GitHub Guides](https://guides.github.com/).
3. In your command prompt / terminal window, change directory to the **global-indicators** folder. Pull new updates from the upstream repository, run:
    ```
    git pull upstream main
    ```
4. Set up analysis environment
  - You could do a local install for the required packages and run our software natively on your own machines.
  - Alternatively, you could use the project docker container to set up the environment (we strongly encourage docker for the easiest working environment due to the complexity of the software stack). For our docker container, run:
    ```
    docker pull globalhealthyliveablecities/global-indicators:latest
    ```
5. Then, check **process** folder for more detail on the 4-step process to calculate spatial indicators of urban design and transport features for healthy and sustainable cities, with data outputs in both geopackage (for mapping) and CSV (without geometry fields, for non-spatial analysis) formats.

The resulting city-specific datasets of spatial indicators of urban design and transport features, calculated at a range of scales from address points, to high resolution grids of the spatial distribution, to overall city summaries can be used to provide evidence to support policy makers and planners to target interventions within cities, compare performance across cities, and when measured across time can be used to monitor progress for achieving urban design goals for reducing inequities. Moreover, they provide a rich source of data for those advocating for disadvantaged and vulnerable community populations, to provide evidence for whether urban policies for where they live are serving their needs.

Our repository (global_scorecards)[https://github.com/global-healthy-liveable-cities/global_scorecards]) provides a framework for reporting on policy and spatial indicators in multiple languages that we developed for creating accessible reports for disseminating findings of our 25-city study. We plan to further update the reporting to work more generally with our ambitions for the 1000 city challenge.  

# How to contribute

#### If you want to contribute to a feature:

  - post your proposal on the [issue tracker](https://github.com/global-healthy-liveable-cities/global-indicators/issues)
  - fork the repo, make your change (adhering to existing coding, commenting, and docstring styles)
  - Create your feature branch: `git checkout -b my-new-feature`
  - Commit your changes: `git commit -am 'Add some feature'`
  - Push to the branch: `git push origin my-new-feature`
  - Submit a pull request.

#### If you've found an error:

  - check the [issues](https://github.com/global-healthy-liveable-cities/global-indicators/issues) first
  - open an new issue in the [issue tracker](https://github.com/global-healthy-liveable-cities/global-indicators/issues) filling out all sections of the template, including a minimal working example or screenshots so others can independently and completely reproduce the problem
