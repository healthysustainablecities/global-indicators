@echo off
echo.
:: Adapted from Geoff Boeing utility script for building a single platform Docker image
::https://github.com/gboeing/osmnx/blob/2631b95a28300ccffce0c7c6838d269ce708ec1a/environments/docker/docker-build-single_platform.sh
set "DOCKERUSER=ryntrnr"
set "PACKAGE=global-indicators-earth-engine"
for /f "usebackq" %%x in ("%CD%\..\.ghsci_version") do set VERSION=%%x
echo %PACKAGE% version %VERSION%
:: login and remove any existing containers or images
docker login

:: build test image and export the conda env to yml
docker build -t %DOCKERUSER%/%PACKAGE% .
docker run --rm -it --net=host -v "%CD%":/home/ghsci %DOCKERUSER%/%PACKAGE% /bin/bash -c "pip list --format=freeze > ./requirements-ee.txt"

:: built multi-platform image
docker buildx create --use
docker buildx build --platform=linux/amd64,linux/arm64 -t %DOCKERUSER%/%PACKAGE%:v%VERSION% . --push
docker buildx rm
