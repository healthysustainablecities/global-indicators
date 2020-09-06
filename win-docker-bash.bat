docker pull gboeing/global-indicators:latest
git pull
docker run --rm -it -v "%cd%":/home/jovyan/work gboeing/global-indicators /bin/bash
