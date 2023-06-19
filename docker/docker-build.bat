@echo off
echo.
:: Adapted from Geoff Boeing utility script for building a single platform Docker image
::https://github.com/gboeing/osmnx/blob/2631b95a28300ccffce0c7c6838d269ce708ec1a/environments/docker/docker-build-single_platform.sh
set "DOCKERUSER=globalhealthyliveablecities"
set "PACKAGE=global-indicators"
for /f "usebackq" %%x in ("%CD%\..\.ghsci_version") do set VERSION=%%x
:: login and remove any existing containers or images
docker login

:: build the image and export the conda env to yml
docker build -t %DOCKERUSER%/%PACKAGE% .
docker run --rm -it --shm-size=2g --net=host -v "%CD%":/home/ghsci globalhealthyliveablecities/global-indicators /bin/bash -c "pip list --format=freeze > ./requirements.txt"

:: get the package version, tag the image with it, then push to hub
echo %PACKAGE% version %VERSION%
docker tag %DOCKERUSER%/%PACKAGE% %DOCKERUSER%/%PACKAGE%:v%VERSION%
docker push -a %DOCKERUSER%/%PACKAGE%
