# Run the script in docker environment

### 1. If you have forked the repo before cloning a local copy to your machine, run
```
git pull upstream master
```

### 2. Download the study region data files shared on Cloudstor and place them in the `/process/data/input` folder.


### 3. Set up analysis environment container and Run bash in this container
  **3.1 Pull this image from docker hub:**
  ```
  Run docker pull gboeing/global-indicators:latest
  ```

  **3.2 *On Windows* open a command prompt and run:**
  ```
  docker run --rm -it -v "%cd%":/home/jovyan/work gboeing/global-indicators /bin/bash
  ```

 **3.2 *On Mac/Linux* open a terminal window and run:**
  ```
  docker run --rm -it -v "$PWD":/home/jovyan/work gboeing/global-indicators /bin/bash
  ```

  * run jupyter notebook

```
docker run --rm -it --name global-indicators -p 8888:8888 -v "$PWD":/home/jovyan/work gboeing/global-indicators

Then, on your computer, open a web browser and visit http://localhost:8888
```

### 4. Change directories to `process` folder.


### 5. Run Python scripts. "true" indicates whether to use multiprocessing or not.
*Note: Need to create study region configuration file if not already exist under `configuration` folder.*    
*Note: Melbourne has the largest number of sample points, which needs 13 GB memory for docker using 3 cpus.*

**5.0 configuration script**   
*The scripts here are used for defining project parameters and preparing all study region configuration json files.*
```
python setup_config.py
```

**5.1 sample point script**
*The scripts here are used for preparing all the fields for sample points.*
```
python sp.py odense.json true
```

**5.2 aggregation script**  
*After generating the sample point statistics, this script will take in a configuration file, which will specify the cities that will serve as input into the aggregation.*
```
python aggr.py cities.json
```

*Note: The sample point script should be run on each of the cities that are being proposed to be aggregated before running the aggregation script. The aggregation script can then be run with a configuration file that references the specific cities.*
