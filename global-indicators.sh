docker pull pgrouting/pgrouting
docker run --name=postgis -d -e POSTGRES_PASSWORD=ghscic -p 5433:5432 --restart=unless-stopped --volume=/var/lib/postgis:/postgresql/13/main pgrouting/pgrouting
docker pull globalhealthyliveablecities/global-indicators:latest
docker run --rm -it --shm-size=2g --net=host -v "$PWD":/home/jovyan/work globalhealthyliveablecities/global-indicators /bin/bash
