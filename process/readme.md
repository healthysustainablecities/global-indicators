# Run the script in docker environment
## Pull this image from docker hub
```
docker pull gboeing/global-indicators
```

#### Run bash in this container

*On Windows* open a command prompt and run:
```
docker run --rm -it -v "%cd%":/home/jovyan/work gboeing/global-indicators /bin/bash
```

*On Mac/Linux* open a terminal window and run:
```
docker run --rm -it -v "$PWD":/home/jovyan/work gboeing/global-indicators /bin/bash
```

#### run Python scripts. "true" indicates whether to use multiprocessing or not. 
#### Notice: Meloubrne has the largest number of sample points, which needs 13 GB memory for docker using 3 cpus.

Change directories to `process` folder.

```
python sv_sp.py odense.json true 
```

```
python sv_aggr.py cities.json
```
