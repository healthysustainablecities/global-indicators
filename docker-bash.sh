docker pull gboeing/global-indicators:latest
git pull
docker run --rm -it --shm-size=2g --net=host -v "$PWD":/home/jovyan/work gboeing/global-indicators /bin/bash
