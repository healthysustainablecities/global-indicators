@echo off
(
:: if Docker exists and is runnable, launch the Docker compose image
    docker compose up -d  && docker attach ghsci
) || (
:: catch
    echo "Please ensure that Docker Desktop is installed and running (https://www.docker.com/products/docker-desktop/). Docker Desktop includes Docker Compose, which is required to run this software."
)
