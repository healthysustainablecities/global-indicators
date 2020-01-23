docker pull zacwang/global-indicator:latest
git pull
docker run --rm -it -v "%cd%":/home/jovyan/work zacwang/global-indicator /bin/bash