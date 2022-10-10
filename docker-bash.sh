docker pull globalhealthyliveablecities/global-indicators:latest
git pull
docker run --rm -it --shm-size=2g --net=host -v "$PWD":/home/jovyan/work globalhealthyliveablecities/global-indicators /bin/bash
