@echo off
echo.
:: Adapted from Geoff Boeing utility script for building a single platform Docker image
::https://github.com/gboeing/osmnx/blob/2631b95a28300ccffce0c7c6838d269ce708ec1a/environments/docker/docker-build-single_platform.sh
set "DOCKERUSER=globalhealthyliveablecities"
set "PACKAGE=global-indicators"
for /f "tokens=2 delims==" %%x in ('findstr /b /c:"GHSCI_VERSION=" "%CD%\..\.env"') do set VERSION=%%x
:: Append '.ee' to the version number
set "VERSION=%VERSION%.ee"
echo %PACKAGE% version %VERSION%
:: login and remove any existing containers or images
docker login

:: Enable BuildKit for better performance and caching
set DOCKER_BUILDKIT=1
set BUILDKIT_PROGRESS=plain

:: build test image with optimizations and export the conda env to yml
docker build -f Dockerfile-ee ^
    -t %DOCKERUSER%/%PACKAGE% .

:: Export requirements using the built image
docker run --rm -it --net=host -v "%CD%":/home/ghsci %DOCKERUSER%/%PACKAGE% /bin/bash -c "pip list --format=freeze > ./requirements-ee.txt"

:: Create buildx instance with optimizations
docker buildx create --use --driver-opt network=host

:: Build multi-platform image with caching and optimizations
docker buildx build -f Dockerfile-ee ^
    --platform=linux/amd64,linux/arm64 ^
    --cache-from %DOCKERUSER%/%PACKAGE%:latest ^
    --cache-to type=inline ^
    --progress=plain ^
    -t %DOCKERUSER%/%PACKAGE%:v%VERSION% ^
    -t %DOCKERUSER%/%PACKAGE%:latest ^
    . --push

:: Cleanup buildx instance
docker buildx rm

echo.
echo Build completed successfully!
echo Image: %DOCKERUSER%/%PACKAGE%:v%VERSION%
echo Latest: %DOCKERUSER%/%PACKAGE%:latest
