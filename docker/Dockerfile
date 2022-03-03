##############################################################################
# Build an image from the dockerfile:
# >>> docker build -t globalhealthyliveablecities/global-indicators:latest .
#
# Run bash in this container and export final conda environment to a yml file:
# >>> docker run --rm -it -v "%cd%":/home/jovyan/work globalhealthyliveablecities/global-indicators /bin/bash
# >>> conda env export -n base > /home/jovyan/work/environment.yml
#
# Push to docker hub
# docker login
# docker tag globalhealthyliveablecities/global-indicators globalhealthyliveablecities/global-indicators:latest
# docker push globalhealthyliveablecities/global-indicators
#
# Run jupyter lab in this container:
# >>> docker run --rm -it -p 8888:8888 -v "%cd%":/home/jovyan/work globalhealthyliveablecities/global-indicators
#
# Stop/delete all local docker containers/images:
# >>> docker stop $(docker ps -aq)
# >>> docker rm $(docker ps -aq)
# >>> docker rmi $(docker images -q) --force
##############################################################################

FROM continuumio/miniconda3
LABEL maintainer="Global Healthy Liveable City Indicator Study Collaboration Group"
LABEL url="https://github.com/global-healthy-liveable-cities/global-indicators"

COPY requirements.txt /tmp/

# add root/bin to path so that tex commands can be run from container
ENV PATH=$PATH:/root/bin

# configure conda and install packages in one RUN to keep image tidy
RUN conda config --set show_channel_urls true && \
	conda config --set channel_priority strict && \
    conda config --prepend channels conda-forge && \
    conda update --yes -n base conda && \
    conda install --update-all --force-reinstall --yes --file /tmp/requirements.txt && \
    conda clean --all --yes && \
    conda info --all && \
    conda list && \
    # install tools for using OpenStreetMap
    apt-get update && apt-get install -y osm2pgsql osmctools && \
    # Install tinytex, a minimal TeX distribution for making pdf documentation
    apt-get update && apt-get install -y perl wget libfontconfig1 && \
    wget -qO- "https://yihui.org/tinytex/install-bin-unix.sh" | sh  && \
    apt-get clean  && \
    tlmgr install xetex xcolor pgf fancyhdr parskip babel-english  \
    units lastpage mdwtools comment   fontawesome times     \
    fncychap titlesec tabulary varwidth wrapfig capt-of needspace  \
    polyglossia fontspec cmap gnu-freefont upquote oberdiek latexmk \
    caption makecell multirow changepage \
    --repository=http://mirror.ctan.org/systems/texlive/tlnet \
    && fmtutil-sys --all && \
    # Install additional LaTeX packages
    # installing seperately to avoid error associated with multirow && \
    # install the make build tools, for compiling sphinx documentation
    apt-get update && apt-get install -y make   && \
    # install the contextily package using pip, required for validation report basemaps
    pip install contextily pillow==9.*

# launch jupyter in the local working directory that we mount
WORKDIR /home/jovyan/work

RUN python -m ipykernel install --name GlobalInd --display-name "Python (GlobalInd)"

# set default command to launch when container is run
CMD ["jupyter", "lab", "--ip='0.0.0.0'", "--port=8888", "--no-browser", "--allow-root", "--NotebookApp.token=''", "--NotebookApp.password=''"]

# to test, import OSMnx and print its version
RUN ipython -c "import osmnx; print(osmnx.__version__)"
