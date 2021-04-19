docker pull globalhealthyliveablecities/global-indicators:latest
git pull
docker run --rm -it --name=global-indicators --shm-size=2g --net=host -v "%cd%":/home/jovyan/work globalhealthyliveablecities/global-indicators /bin/bash
