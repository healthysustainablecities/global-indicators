########################################################################
#
# Build an image from the dockerfile:
# >>> docker build -t gboeing/global-indicators .
#
# Run bash in this container and export final conda environment to a yml file:
# >>> docker run --rm -it -v "%cd%":/home/jovyan/work gboeing/global-indicators /bin/bash
# >>> conda env export -n base > /home/jovyan/work/environment.yml
# 
# Push to docker hub
# docker login
# docker tag gboeing/global-indicators gboeing/global-indicators:v0
# docker push gboeing/global-indicators
#
# Run jupyter lab in this container:
# >>> docker run --rm -it -p 8888:8888 -v "%cd%":/home/jovyan/work gboeing/global-indicators
#
# Stop/delete all local docker containers/images:
# >>> docker stop $(docker ps -aq)
# >>> docker rm $(docker ps -aq)
# >>> docker rmi $(docker images -q) --force
########################################################################

FROM continuumio/miniconda3
LABEL maintainer="Geoff Boeing <boeing@usc.edu>"
LABEL url="https://github.com/gboeing/global-indicators"

COPY requirements.txt /tmp/

# configure conda and install packages in one RUN to keep image tidy
RUN conda config --set show_channel_urls true && \
	conda config --set channel_priority strict && \
    conda config --prepend channels conda-forge && \
    conda update --yes -n base conda && \
    conda install --update-all --force-reinstall --yes --file /tmp/requirements.txt && \
    conda clean --all --yes && \
    conda info --all && \
    conda list

# install tools for using OpenStreetMap
RUN apt-get update && apt-get install -y osm2pgsql osmctools

# Install tinytex, a minimal TeX distribution for making pdf documentation
RUN apt-get update && apt-get install -y perl wget libfontconfig1 && \
    wget -qO- "https://yihui.org/tinytex/install-bin-unix.sh" | sh  && \
    apt-get clean

# Install LaTeX packages
RUN /root/bin/tlmgr install xetex xcolor pgf fancyhdr parskip babel-english  \ 
    units lastpage mdwtools comment   fontawesome times     \
    fncychap titlesec tabulary varwidth wrapfig capt-of needspace  \
    polyglossia fontspec cmap gnu-freefont upquote oberdiek latexmk \
    --repository=http://mirror.ctan.org/systems/texlive/tlnet \
 && /root/bin/fmtutil-sys --all

# Install additional LaTeX packages
# installing seperately to avoid error associated with multirow
tlmgr install caption makecell --repository=http://mirror.ctan.org/systems/texlive/tlnet 
tlmgr install multirow --repository=http://mirror.ctan.org/systems/texlive/tlnet 

# install the make build tools, for compiling sphinx documentation
RUN apt-get update && apt-get install -y make

# add root/bin to path so that tex commands can be run from container
ENV PATH=$PATH:/root/bin

# launch jupyter in the local working directory that we mount
WORKDIR /home/jovyan/work

RUN python -m ipykernel install --name GlobalInd --display-name "Python (GlobalInd)"

# set default command to launch when container is run
CMD ["jupyter", "lab", "--ip='0.0.0.0'", "--port=8888", "--no-browser", "--allow-root", "--NotebookApp.token=''", "--NotebookApp.password=''"]

# to test, import OSMnx and print its version
RUN ipython -c "import osmnx; print(osmnx.__version__)"

