# Run the script in docker environment

### 1. If you have forked the repo before cloning a local copy to your machine, run
```
git pull upstream master
```

### 2. Download the study region data files shared on Cloudstor and place them in the `/process/data` folder.


### 3. Set up analysis environment container and Run bash in this container
*Pull this image from docker hub*
```
Run docker pull gboeing/global-indicators:latest
```

*On Windows* open a command prompt and run:
```
docker run --rm -it -v "%cd%":/home/jovyan/work gboeing/global-indicators /bin/bash
```

*On Mac/Linux* open a terminal window and run:
```
docker run --rm -it -v "$PWD":/home/jovyan/work gboeing/global-indicators /bin/bash
```

### 4. Change directories to `process` folder.


### 5. run Python scripts. "true" indicates whether to use multiprocessing or not.
*Note: Need to create study region configuration file if not already exist under `configuration` folder.*    
*Note: Meloubrne has the largest number of sample points, which needs 13 GB memory for docker using 3 cpus.*    

#### sample point scripts  
The scripts here are used for preparing all the fields for sample points.
```
python sv_sp.py odense.json true
```

#### aggregation scripts  
After generating the sample point statistics, this script will take in a configuration file, which will specify the cities that will serve as input into the aggregation.
```
python sv_aggr.py cities.json
```

*Note: The sample point script should be run on each of the cities that are being proposed to be aggregated before running the aggregation script. The aggregation script can then be run with a configuration file that references the specific cities.*
