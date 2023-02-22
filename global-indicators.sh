if [ -x "$(command -v docker)" ]; then
    # if Docker exists and is runnable, launch the Docker compose image
    docker compose up -d
    # attach to the GHSCI software process
    docker attach ghsci
else
    echo "Install docker"
    # command
fi
