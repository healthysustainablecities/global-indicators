docker pull gboeing/global-indicators:latest
git pull
docker run --rm -it -v "$PWD$":/home/jovyan/work gboeing/global-indicators /bin/bash
