#!/bin/bash
# Adapted from Geoff Boeing utility script for building a single platform Docker image
#https://github.com/gboeing/osmnx/blob/2631b95a28300ccffce0c7c6838d269ce708ec1a/environments/docker/docker-build-single_platform.sh
DOCKERUSER=globalhealthyliveablecities
PACKAGE=global-indicators
VERSION=$(cat "../.ghsci_version")
# login and remove any existing containers or images
docker login
docker stop $(docker ps -aq)
# docker rm $(docker ps -aq)
# docker rmi $(docker images -q) --force

# build the image and export the conda env to yml
set -e
docker build -t $DOCKERUSER/$PACKAGE .
docker run --rm -it --shm-size=2g --net=host -v "$PWD":/home/ghsci globalhealthyliveablecities/global-indicators /bin/bash "pip list --format=freeze > /home/ghsci/docker/requirements.txt"

# get the package version, tag the image with it, then push to hub
echo "$PACKAGE version $VERSION"
docker tag $DOCKERUSER/$PACKAGE $DOCKERUSER/$PACKAGE:v$VERSION
docker push -a $DOCKERUSER/$PACKAGE
