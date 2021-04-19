# Running the Process
Please follow the instructions below to run the process.

## Run the Python Scripts

### 1. Fork the Repo
- Make sure that you have forked the repo onto your own GitHub account and that the repository is cloned onto your machine.
- Additionally, to make sure that your branch is up to date run the following in your command prompt / terminal window
    1. Change directory to the **global-indicators** folder on your machine
    1. Type the following:
        ```
        git pull upstream main
      ```

### 2. Set up project and study region parameter configuration
Project and study region specific parameters are defined external to the code using configuration files. These can be accessed and customized in ``setup_config.py`` to incorporate different study regions and data sources, or re-parameterize for a new project with distinct requirements and outcomes of interest. Make sure you have setup the project configuration before proceeding the analysis.

### 2. Download and Pre-process Data
1.  Raw data should be downloaded and pre-processed following a series of Python scripts within **pre_process** folder to prepare study region-specific GeoPackages used as input for the main analysis workflow.
1.  Once all input data are prepared, create a folder named **input** in **global-indicators/process/data** to store the input data.
1.  Create a second subfolder (this will be empty initially) named **output** in **global-indicators/process/data**.

### 3. Run Docker
1.  In the command prompt / terminal window, change your directory to the **global-indicators** folder. Then type the following
    ```
    Docker pull globalhealthyliveablecities/global-indicators:latest
    ```
1.  Start running docker in your machine
    - On Windows:
        ```
        docker run --rm -it -v "%cd%":/home/jovyan/work globalhealthyliveablecities/global-indicators /bin/bash
        ```
    - On Mac/Linux:
        ```
        docker run --rm -it -v "$PWD":/home/jovyan/work globalhealthyliveablecities/global-indicators /bin/bash
        ```
1. Change directory to **global-indicators/process**

### 4. Run the Python Scripts
1.  Run scripts using the following code
    1.  ```python setup_config.py```
        1. Make sure to check on the list of cities within the ``setup_config.py``, it should include cities that you plan to analyze  
            1. Add a pound sign (#) before each city you do NOT wish to include in your analysis
    1.  ```python sp.py [SPECIFIC CITY NAME]```
        1.  Use the file name that can be found under the **process/configuration** folder for each city. Example: For Mexico City, type ```python sp.py mexico_city```
        1.  Alternatively, a shell script wrapper **process_regions.sh** exists to run all study regions at once in sequence, and can be run using ```bash process_regions.sh``` followed by a list of region names. For example,  ```bash process_regions.sh adelaide hong_kong vic```
        1.  Make sure to run this line of code for every city that you wish to include before running ``aggr.py`` script
    1.  ```python aggr.py```
        1. If you do not wish to find the aggregate of all cities, make sure to ``setup_config.py`` is updated to reflect the cities that you would like to include.
        1. Notice that you will get the final indicator geopackadge in **global-indicators/process/data/output** only after you run this ``aggr.py`` script

Note that it will take several hours to run these scripts, depending on the size of the study city. Also, the process requires a machine with more than 8 GB of memory in order to successfully run the largest cities.

## Run the Jupyter Notebooks

1. Follow steps 1 and 2 from the instructions above
1. Run docker:
    - On Windows:
          ```
          docker run --rm -it --name global-indicators -p 8888:8888 -v "%cd%":/home/jovyan/work globalhealthyliveablecities/global-indicators
          ```
    - On Mac/Linux:
         ```
         docker run --rm -it --name global-indicators -p 8888:8888 -v "$PWD":/home/jovyan/work globalhealthyliveablecities/global-indicators
        ```
2. Open a web browser and visit http://localhost:8888
3. Run the Jupyter Notebooks

Note that it will take several hours to several days to run these scripts, depending on the size of the study city.
