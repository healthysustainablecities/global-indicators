# set up analysis environment container, based on OSMnx
cd ./process/docker
docker build -t ind_bangkok .
cd ../..

# set up spatial database container, based on Postgis
docker pull mdillon/postgis

# run postgis server container
docker run --name=postgis -d -e POSTGRES_USER=postgres -e POSTGRES_PASS=huilhuil!42 -e POSTGRES_DBNAME=ind_bangkok  -p 127.0.0.1:5433:5432 -e pg_data:/var/lib/postgresql mdillon/postgis

# run analysis environment as Bash command prompt
docker run --rm -it -u 0 --name ind_bangkok --net=host -v %cd%:/home/jovyan/work ind_bangkok /bin/bash 

# run analysis environment as Jupyter Lab (note - not yet conversing properly with database)
docker run --rm -it --name ind_bangkok -p 8888:8888  -p 5433:5433 -v %cd%:/home/jovyan/work ind_bangkok