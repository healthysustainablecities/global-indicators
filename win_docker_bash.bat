docker pull zacwang/global-indicator:latest
git pull
docker run --rm -it -u 0 --name global-indicators -v "%cd%":/home/jovyan/work zacwang/global-indicator /bin/bash