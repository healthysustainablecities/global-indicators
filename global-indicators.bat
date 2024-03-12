@echo off
echo.
echo Global Healthy and Sustainable City Indicators
for /f "usebackq" %%x in ("%CD%\.ghsci_version") do set VERSION=%%x
echo %VERSION%
echo.
echo https://healthysustainablecities.org ('1000 Cities Challenge')
echo https://global-healthy-liveable-cities.github.io/ (Software guide)
echo.
(
:: if Docker exists and is runnable, launch the Docker compose image
    docker compose -f docker-compose.yml up -d  && docker attach ghsci
) || (
:: catch
    echo "Please ensure that Docker Desktop is installed and running (https://www.docker.com/products/docker-desktop/). Docker Desktop includes Docker Compose, which is required to run this software."
)
