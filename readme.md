# Global liveability indicators project

## Background
RMIT University, in collaboration with researchers from other universities worldwide, is undertaking a project, the Global Indicators Project, to calculate health-related spatial built environment indicators for 25 cities globally; The project aims to make use of open data sources, such as OpenStreetMap (OSM), the Global Human Settlement Layer (GHSL), and GTFS feeds (where available) as input to the indicator processing. After indicators have been derived for a city, members of the team and study region collaborators who have local knowledge of that city will validate these indicators.  

This (proposed) repository contains documentation and process scripts used for calculating the global liveability indicators in the (['Lancet series'][https://www.thelancet.com/journals/lancet/article/PIIS0140-6736(15)01284-2/fulltext)] project, 2019.  

The processes are developed to create indicators for our selected global cities (with the potential that these processes could be applied to other study region globally). These indicators are:   
1. Population per square kilometre  
2. Street connectivity per square kilometre  
3. Access to supermarkets within 500 metres  
4. Access to convenience stores within 500 metres  
5. Access to a public transport stop (any mode) within 500 metres  
6. Access to public open space (e.g. parks) within 500 metres  
7. Access to a frequent public transport stop (any mode) within 500 metres  
8. Daily living score within 500 metres (within and across cities)
9. Walkability scores (within and across cities)

## Documentation
Please refer to the documentation folder readme for more information about this repository.

# How to set up and get started?

1. install [Git](https://git-scm.com/downloads) and [Docker](https://www.docker.com/products/docker-desktop)
1. git clone https://github.com/gboeing/global-indicators.git, or fork the repo and then git clone a local copy to your machine
1. for update run from the forked repository:
```
git pull upstream master
```
1. set up analysis environment container
```
Run docker pull gboeing/global-indicators:latest
```
1. Download the study region data files shared on [Cloudstor](https://cloudstor.aarnet.edu.au/plus/s/j1UababLcIw8vbM), and place them in the `/process/data/input` folder.

1. Then, check `process` folder for more detail script running process

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