docker pull pgrouting/pgrouting
docker run --name=postgis -d -e POSTGRES_PASSWORD=ghscic -p 5433:5432 --restart=unless-stopped --volume=/var/lib/postgis:/postgresql/13/main pgrouting/pgrouting