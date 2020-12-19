# global-indicators

A open-source tool in python to compute pedestrian accessibility indicators for cities worldwide using open data, such as OpenStreetMap (OSM), the Global Human Settlement Layer (GHSL), and GTFS feeds (where available).

This tool presents a generalized method to measure pedestrian accessibility indicators within- and between-city at both city scale and high-resolution grid level. The methodology and the open data approach developed in this research can be expanded to many cities worldwide to support local policy making towards healthy and sustainable living environments.

The process scripts enable computation of the following indicators of pedestrian accessibility:
1. Urban area in square kilometers
2. Population size and population density  
3. Street connectivity: intersections per square kilometer
4. Access to destinations: population access within 500 meters walking distance to:  
    - a supermarkets
    - a convenience store
    - any public open space (e.g. parks)
    - any public transport stop (any mode)
5. Daily living score (within and across cities)
6. Walkability index (within and across cities)

## Documentation
Please refer to the documentation folder readme for more information about this repository.

# How to set up and get started?

1. Install [Git](https://git-scm.com/downloads) and [Docker](https://www.docker.com/products/docker-desktop)
1. Git clone https://github.com/gboeing/global-indicators.git, or fork the repo and then git clone a local copy to your machine. For help on this, please refer to the [GitHub Guides](https://guides.github.com/).
1. In your command prompt / terminal window, change directory to the **global-indicators** folder. Pull new updates from the upstream repository, run:
    ```
    git pull upstream master
    ```
1. Set up analysis environment container, run:
    ```
    docker pull gboeing/global-indicators:latest
    ```
2. Then, check **process** folder for more detail script running process

## Data
Retrieve the data from the links found in the following google doc:
https://docs.google.com/document/d/1NnV3g8uj0OnOQFkFIR5IbT60HO2PiF3SLoZpUUTL3B0/edit?ts=5ecc5e75

# How to contribute

#### If you want to contribute to a feature:

  - post your proposal on the [issue tracker](https://github.com/gboeing/global-indicators/issues)
  - fork the repo, make your change (adhering to existing coding, commenting, and docstring styles)
  - Create your feature branch: `git checkout -b my-new-feature`
  - Commit your changes: `git commit -am 'Add some feature'`
  - Push to the branch: `git push origin my-new-feature`
  - Submit a pull request.

#### If you've found an error:

  - check the [issues](https://github.com/gboeing/global-indicators/issues) first
  - open an new issue in the [issue tracker](https://github.com/gboeing/global-indicators/issues) filling out all sections of the template, including a minimal working example or screenshots so others can independently and completely reproduce the problem