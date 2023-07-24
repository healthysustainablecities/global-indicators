##############################################################################
# Build an image from the dockerfile:
# >>> docker build -t globalhealthyliveablecities/global-indicators:latest .
#
# Run bash in this container from main project folder and export package versions to Docker/requirements.txt:
# >>> docker run --rm -it --shm-size=2g --net=host -v "$PWD":/home/ghsci/work globalhealthyliveablecities/global-indicators /bin/bash
# >>> pip list --format=freeze > ./Docker/requirements.txt
#
# Push to docker hub
# docker login
# docker tag globalhealthyliveablecities/global-indicators globalhealthyliveablecities/global-indicators:latest
# docker tag globalhealthyliveablecities/global-indicators globalhealthyliveablecities/global-indicators:yyyy-mm-dd
# docker push --all-tags globalhealthyliveablecities/global-indicators
#
# Stop/delete all local docker containers/images:
# >>> docker stop $(docker ps -aq)
# >>> docker rm $(docker ps -aq)
# >>> docker rmi $(docker images -q) --force
##############################################################################

FROM continuumio/miniconda3:23.3.1-0-alpine as build
LABEL maintainer="Global Healthy Liveable City Indicator Study Collaboration Group"
LABEL url="https://github.com/global-healthy-liveable-cities/global-indicators"

COPY environment.yml .

# add root/bin to path so that tex commands can be run from container
ENV PATH=$PATH:/root/bin

# Install conda pack
RUN conda config --set show_channel_urls true && \
	conda config --set channel_priority strict && \
    conda config --prepend channels conda-forge && \
    conda update --yes -n base conda && \
    conda install -c conda-forge conda-pack && \
    conda env create -n env -f environment.yml && \
    conda pack -n env -o env.tar.gz && \
    conda list -n env --explicit > spec-file.txt

# =============================================================================
# Runtime environment
FROM debian:bullseye-slim as runtime

# Install the environment pack
COPY --from=build /env.tar.gz .
RUN mkdir /env && \
    tar xvzf /env.tar.gz -C /env && \
    rm -rv /env.tar.gz && \
    /env/bin/python /env/bin/conda-unpack && \
    useradd -u 8877 ghsci && \
    # install tools for using OpenStreetMap
    apt-get update && apt-get install -y git osm2pgsql osmctools

ENV PATH="/env/bin/:$PATH"
ENV PROJ_LIB="/env/share/proj"

RUN pip install -e git+https://github.com/wklumpen/gtfs-lite.git#egg=gtfs-lite && \
    pip install -e git+https://github.com/anerv/BikeDNA_BIG#egg=src && \
    echo 'alias configure="python configure.py"' >> ~/.bashrc && \
    echo 'alias analysis="python analysis.py"' >> ~/.bashrc && \
    echo 'alias generate="python generate.py"' >> ~/.bashrc && \
    echo 'alias compare="python compare.py"' >> ~/.bashrc  && \
    echo 'alias ghsci="python gui.py"' >> ~/.bashrc && \
    echo 'alias help="cat ../help.txt"' >> ~/.bashrc && \
    echo 'alias lab="jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --notebook-dir=/home/ghsci/process --allow-root"' >> ~/.bashrc && \
    echo 'export PS1="# "' >> ~/.bashrc

USER ghsci
WORKDIR /home/ghsci
