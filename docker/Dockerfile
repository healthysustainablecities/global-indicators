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
# docker push globalhealthyliveablecities/global-indicators
#
# Stop/delete all local docker containers/images:
# >>> docker stop $(docker ps -aq)
# >>> docker rm $(docker ps -aq)
# >>> docker rmi $(docker images -q) --force
##############################################################################

FROM continuumio/miniconda3:4.10.3-alpine as build
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
    apt-get update && apt-get install -y osm2pgsql osmctools
    # && \
    ## Install tinytex, a minimal TeX distribution for making pdf documentation
    #apt-get update && apt-get install -y perl wget libfontconfig1 && \
    #wget -qO- "https://yihui.org/tinytex/install-bin-unix.sh" | sh  && \
    #apt-get clean  && \
    #tlmgr install xetex xcolor pgf fancyhdr parskip babel-english  \
    #units lastpage mdwtools comment   fontawesome times     \
    #fncychap titlesec tabulary varwidth wrapfig capt-of needspace  \
    #polyglossia fontspec cmap gnu-freefont upquote oberdiek latexmk \
    #caption makecell multirow changepage \
    #--repository=http://mirror.ctan.org/systems/texlive/tlnet \
    #&& fmtutil-sys --all && \
    ## Install additional LaTeX packages
    ## installing seperately to avoid error associated with multirow && \
    ## install the make build tools, for compiling sphinx documentation
    #apt-get update && apt-get install -y make   && \
    #install the contextily package using pip, required for validation report basemaps &&\
    #pip install contextily pillow==9.*

USER ghsci
ENV PATH="/env/bin/:$PATH"
ENV PROJ_LIB="/env/share/proj"

WORKDIR /home/ghsci/work
