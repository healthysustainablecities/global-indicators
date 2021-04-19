docker pull globalhealthyliveablecities/global-indicators:latest
git pull
docker run --rm -it -p 8888:8888 -v "$PWD":/home/jovyan/work globalhealthyliveablecities/global-indicators
