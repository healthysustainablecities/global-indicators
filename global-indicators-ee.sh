#!/usr/bin/env bash
echo
echo Global Healthy and Sustainable City Indicators
VERSION="$(cat "$PWD/.ghsci_version")"
# Append '.ee' to the version number
VERSION="${VERSION}.ee"
echo "$VERSION"
echo
echo https://healthysustainablecities.org \('1000 Cities Challenge'\)
echo https://github.com/healthysustainablecities/global-indicators/wiki \(Software guide\)
echo
{ # try
    # Launch Docker container
    docker compose -f docker-compose-ee.yml up -d && {
        echo
        echo "Docker container started successfully."
        echo
        echo "Running Earth Engine authentication..."
        echo
        
        # Run the authentication script inside the container before attaching
        docker exec -it ghsci-ee python /home/ghsci/process/subprocesses/authenticate-ee.py
        
        # Attach to the Docker container
        docker attach ghsci-ee
    }
} || { # catch
    echo "Please ensure that Docker Desktop is installed and running (https://www.docker.com/products/docker-desktop/). Docker Desktop includes Docker Compose, which is required to run this software."
}
