# Project docker image

## Pull this image from docker hub
```
docker pull globalhealthyliveablecities/global-indicators
```

## Run bash in this container

*On Windows* open a command prompt and run:
```
docker run --rm -it -v "%cd%":/home/jovyan/work globalhealthyliveablecities/global-indicators /bin/bash
```

*On Mac/Linux* open a terminal window and run:
```
docker run --rm -it -v "$PWD":/home/jovyan/work globalhealthyliveablecities/global-indicators /bin/bash
```
