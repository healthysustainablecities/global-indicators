# Project docker image

## Pull this image from docker hub
```
docker pull zacwang/global-indicator
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

## Run jupyter in this container

*On Windows* open a command prompt, change directory to location of notebook file, and run:
```
docker run --rm -it --name global-indicators -p 8888:8888 -v %cd%:/home/jovyan/work gboeing/global-indicators
```

*On Mac/Linux* open a terminal window, change directory to location of notebook file, and run:
```
docker run --rm -it --name global-indicators -p 8888:8888 -v "$PWD":/home/jovyan/work gboeing/global-indicators
```

Then, on your computer, open a web browser and visit http://localhost:8888
