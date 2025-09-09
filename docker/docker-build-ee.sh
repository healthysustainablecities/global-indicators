#!/bin/bash
# Adapted from Geoff Boeing utility script for building a single platform Docker image
#https://github.com/gboeing/osmnx/blob/2631b95a28300ccffce0c7c6838d269ce708ec1a/environments/docker/docker-build-single_platform.sh
DOCKERUSER=globalhealthyliveablecities
PACKAGE=global-indicators
VERSION=$(grep '^GHSCI_VERSION=' ../.env | cut -d '=' -f2-)
# Append '.ee' to the version number
VERSION="${VERSION}.ee"
echo "${PACKAGE} version ${VERSION}"
# login and remove any existing containers or images
docker login

# build the image and export the conda env to yml
set -e # exit if any command has a non-zero exit status (ie. an error)
# specify -f Dockerfile-ee
docker build -f Dockerfile-ee -t $DOCKERUSER/$PACKAGE .
docker run --rm -it -v "$PWD":/home/ghsci $DOCKERUSER/$PACKAGE /bin/bash -c "pip list --format=freeze > ./requirements-ee.txt"

# build and push multi-platform image, drawing on cached preliminary build
docker buildx create --use
# specify -f Dockerfile-ee
docker buildx build -f Dockerfile-ee --platform=linux/amd64,linux/arm64 -t  $DOCKERUSER/$PACKAGE:v$VERSION . --push
docker buildx rm
