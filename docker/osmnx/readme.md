# Project docker image

## Pull this image from docker hub
```
docker pull gboeing/global-indicators
```

## Run bash in this container
```
docker run --rm -it -u 0 --name global-indicators -v %cd%:/home/jovyan/work gboeing/global-indicators /bin/bash
```

## Run jupyter in this container
```
docker run --rm -it --name global-indicators -p 8888:8888 -v %cd%:/home/jovyan/work gboeing/global-indicators
```

Then on your computer, open a web browser and visit http://localhost:8888
