# Project docker image

## Pull this image from docker hub
```
docker pull gboeing/global-indicators
```

## Run bash in this container

*On Windows* open a command prompt and run:
```
docker run --rm -it -u 0 --name global-indicators -v %cd%:/home/jovyan/work zacwang/global-indicator /bin/bash
```

*On Mac/Linux* open a terminal window and run:
```
docker run --rm -it -u 0 --name global-indicators -v "$PWD":/home/jovyan/work zacwang/global-indicator /bin/bash
```
