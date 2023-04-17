@echo off
echo.
echo Global Healthy and Sustainable City Indicators
FOR /f "usebackq" %%x in ("%CD%\.ghsci_version") do (echo %%x)
echo.
echo https://healthysustainablecities.org ('1000 Cities Challenge')
echo https://global-healthy-liveable-cities.github.io/ (Software guide)
echo.
echo To run the provided example analysis for Las Palmas, Spain, enter:
echo python 1_create_project_configuration_files.py example_ES_Las_Palmas_2023
echo python 2_analyse_region.py example_ES_Las_Palmas_2023
echo python 3_generate_resources.py example_ES_Las_Palmas_2023
echo.
echo For more directions on each step, without specifying a study region.
echo.
echo To exit, type and enter: exit
echo.
(
:: if Docker exists and is runnable, launch the Docker compose image
    docker compose -f docker-compose.yml up -d  && docker attach ghsci
) || (
:: catch
    echo "Please ensure that Docker Desktop is installed and running (https://www.docker.com/products/docker-desktop/). Docker Desktop includes Docker Compose, which is required to run this software."
)
echo.
