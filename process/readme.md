# Running the Process
Please follow the instructions below to run the process. 

## Run the Python Scripts

### 1. Fork the Repo
- Make sure that you have forked the repo onto your own GitHub account and that the repository is cloned onto your machine. For help on this, please refer to the [GitHub Guides](https://guides.github.com/). 
- Additionally, to make sure that your branch is up to date run the following in your command prompt / terminal window
    1. Change directory to the global-indicators folder on your machine
    1. Type git pull upstream master

### 2. Download and Organize the Data
1.  Download the global data from the cloudstor data folder. You can find the links to this data [HERE](https://docs.google.com/document/d/1NnV3g8uj0OnOQFkFIR5IbT60HO2PiF3SLoZpUUTL3B0/edit?ts=5ecc5e75).
1.  Rename the folder to ‘input’ and place the folder of data in ‘global-indicators/process/data’. 
1.  Create a second folder (this will one will be empty initially), named ‘output’. This should also be placed in ‘global-indicators/process/data’.

### 3. Run Docker
1.  In the command prompt / terminal window, change your directory to the global-indicators folder. Then type the following
    1.  Docker pull gboeing/global-indicators:latest
1.  Start running docker in your machine
    - On Windows:
        - docker run --rm -it -v "%cd%":/home/jovyan/work gboeing/global-indicators /bin/bash
    - On Mac/Linux:
        - docker run --rm -it -v "$PWD":/home/jovyan/work gboeing/global-indicators /bin/bash
1. Change directory to to ‘global-indicators/process’

### 4. Run the Python Scripts 
1.  Run scripts using the following code
    1.  python setup_config.py
    1.  python sp.py [SPECIFIC CITY NAME].json true
        1.  Use the file name that can be found under the process/configuration folder for each city. Example: For Adelaide, type ‘python sp.py Adelaide.json true’
        1.  Only type true if using multiprocessing. On machines with lower capacity, we recommend not including ‘true’ in the command. So, for Adelaide, type ‘python sp.py Adelaide.json'
        1.  Make sure to run this line of code for each city before running aggr.py script
    1.  Type python aggr.py cities.json

Note that it will take several hours to several days to run these scripts, depending on the size of the study city. 

Alternatively, if you would like to run only specific cities for the process, please do the following before running the aggregation script aggr.py. 
1.  Go into the configuration folder and open the cities.json file
    1.  Save as ‘originalcities.json’ in the configuration folder. This will serve as a backup copy of the original file for future use
    1.  In cities.json, now delete the cities that are not to be included in your analysis. They will be found in lines 3-26
    1.  Save file
1.  In the process folder, open setup_config.py
    1.  In lines 20-43, add a pound sign (#), before each city you would like to NOT include in your analysis
    1.  Save file
1.  Run aggr.py script

## Run the Jupyter Notebooks

1. Follow steps 1 and 2 from the instructions above
1. Run docker:
    1. In the command prompt / terminal window, change your directory to the global-indicators folder. Then type the following
        1. docker run --rm -it --name global-indicators -p 8888:8888 -v "$PWD":/home/jovyan/work gboeing/global-indicators
1. Open a web browser and visit http://localhost:8888
1. Run the Jupyter Notebooks

