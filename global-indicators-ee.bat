@echo off
echo.
echo Global Healthy and Sustainable City Indicators
for /f "usebackq" %%x in ("%CD%\.ghsci_version") do set VERSION=%%x
:: Append '.ee' to the version number
set VERSION=%VERSION%.ee  
echo %VERSION%
echo.
echo https://healthysustainablecities.org ('1000 Cities Challenge')
echo https://healthysustainablecities.github.io/software/ (Software guide)
echo.

:: Try to launch Docker container
(
    docker compose -f docker-compose-ee.yml up -d && (
        echo.
        echo Docker container started successfully.
        echo.
        echo Running Earth Engine authentication...
        echo.
        
        :: Run the authentication script inside the container before attaching
        docker exec -it ghsci-ee python /home/ghsci/process/subprocesses/authenticate-ee.py
        
        :: Attach to the Docker container
        docker attach ghsci-ee
    )
) || (
    :: catch
    echo "Please ensure that Docker Desktop is installed and running (https://www.docker.com/products/docker-desktop/). Docker Desktop includes Docker Compose, which is required to run this software."
    exit /b 1
)