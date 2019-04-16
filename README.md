# Global liveability indicators project#

This (proposed) repository contains documentation and processes used in the global liveability indicators ('Lancet series') project, 2019.

### How do I get set up? ###

* install [Git](https://git-scm.com/downloads) and [Docker](https://www.docker.com/products/docker-desktop)

* git clone https://carlhiggs@bitbucket.org/carlhiggs/ind_global.git

* set up analysis environment container, based on OSMnx

```
cd ./process/docker
docker build -t ind_global .
cd ../..
```

* set up spatial database container, based on Postgis

```
docker pull mdillon/postgis
```


* run postgis server container

```
docker run --name=postgis -d -e POSTGRES_USER=postgres -e POSTGRES_PASS=password -e POSTGRES_DBNAME=ind_global  -p 127.0.0.1:5433:5432 -e pg_data:/var/lib/postgresql mdillon/postgis
```

* run analysis environment from Bash

```
docker run --rm -it -u 0 --name ind_global --net=host -v %cd%:/home/jovyan/work ind_global /bin/bash 
```

### Progress ###
The scripts in the 'process' folder have been brought in from a seperate Australia based national project.  They are in the process of being re-factored for a more stream-lined and generalised workflow using the Bangkok branch.

This master branch is a proposed location for updates for the broader global indicators project, however modifications will be required to be made to the Bangkok implementation to work in global context
(e.g. study region configuration, which for Bangkok's purposes no longer functions as directly as it did for the national project, so will have to be re-implemented if we choose to use the scripts as a basis for our work).

See the Bangkok branch for indication on which scripts have been updated for that project.  Seperately, if we choose to adopt the structure of this approach for the global project, we should track which parts have been updated in a similar list below perhaps.

### Contact ###

carl.higgs@rmit.edu.au

liu.shiqi@husky.neu.edu

g.boeing@northeastern.edu

