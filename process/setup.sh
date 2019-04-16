# The following installation directions are for Unix
# This can be run on Windows using the Windows Subsystem for Linux (WSL)
# see https://docs.microsoft.com/en-us/windows/wsl/faq

# The reason for this is to help ensure a stable, universal environment for replicable analyses.

# Retrieve, install and update the Anaconda Python distribution
wget https://repo.anaconda.com/archive/Anaconda3-2018.12-Linux-x86_64.sh
bash Anaconda3-2018.12-Linux-x86_64.sh
export PATH=~/anaconda3/bin:$PATH
conda update conda

# Create virtual environment for project, including required libraries for analyses
conda create -c conda-forge -n ind_bangkok \
    python=3.7.3                           \
    gdal                                   \
    osmnx=0.9                              \
    rasterstats                            \
    geoalchemy2                            \
    rasterstats                            \
    geopandas                              \
    postgresql=10.5                        \
    postgis                                \
    proj4                                  \
    ipyleaflet 

## Possibly: docker pull gboeing/osmnx  ???
    
Finally, to get things fully working, we enter the newly created virtual environment to make sure some more packages are installed (as they don't seem to be fully installed from purely running the above):
activate ntnl_li
pip install altair
pip install rasterio
pip install osmnx
pip install rasterstats
pip install xlrd
pip install geoalchemy2
conda upgrade numpy
(click 'y' if required to proceed)

Now, you can close this command window, and relaunch it (you don't need administrator mode necessarily now).

Re-open cmd.exe and navigate to the project script folder, D:\ntnl_li_2018_template\process

To use the create_pedestrian_networks.py script it is assumed that you have
set up your new study region in the project configuration file (project_configuration.xlsx)
run the following, say for Mildura:
  python 00_create_database.py mildura 
  python 01_study_region_setup.py mildura
  
Now we need to make sure you have the required OSM data; please copy the folder 'osm' from the network drive GIS/data/ folder to your D: drive  (not the most elegant solution, but this is what we currently do).  This contains a 'planet_archives' sub-folder, within which is the OSM data we use in our project.  The project config file points to  'D:/osm/planet_archives/planet-latest_20181001.osm.pbf' to find this.
  
Now, you activate the virtual environment and then run the new script with this special version of Python which contains all the project-specific dependencies we set up before
  activate ntnl_li
  python create_pedestrian_networks.py mildura 

For larger cities in particular, this script will take some time.
 '''