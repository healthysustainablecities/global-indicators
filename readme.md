# Global liveability indicators project

### Background
RMIT University, in collaboration with researchers from other universities worldwide, is undertaking a project, the Global Indicators Project, to calculate 10 health-related spatial indicators for 25 cities globally; The project aims to make use of open data sources, such as OpenStreetMap, the Global Human Settlement Layer, and GTFS feeds (where available) as input to the indicator processing. After indicators have been derived for a city, members of the team who have local knowledge of that city will validate these.  

This (proposed) repository contains documentation and processes used in the global liveability indicators ('Lancet series') project, 2019.  

The processes are to be developed to create indicators for our selected global cities. The indicators are:   
1. Population per square kilometre  
2. Street connectivity per square kilometre  
3. Access to supermarkets within 500 metres  
4. Access to convenience stores within 500 metres  
5. Access to a public transport stop (any mode) within 500 metres  
6. Access to public open space (e.g. parks) within 500 metres  
7. Access to a frequent public transport stop (any mode) within 500 metres  
8. Daily living score within 500 metres  
9. Walkability relative to study region  
10. Walkability relative to all cities  


### How to set up and get started? ###

* install [Git](https://git-scm.com/downloads) and [Docker](https://www.docker.com/products/docker-desktop)

* git clone https://github.com/gboeing/global-indicators.git, or fork the repo and then git clone a local copy to your machine

* for update run from the forked repository:
```
git pull upstream master
```

* set up analysis environment container

```
Run docker pull gboeing/global-indicators:latest
```

* Download the study region data files shared on [Cloudstor](https://cloudstor.aarnet.edu.au/plus/s/j1UababLcIw8vbM) and place them in the `/process/data` folder.

* Then, check `process` folder for more detail script running process
