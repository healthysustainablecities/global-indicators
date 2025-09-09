FROM continuumio/miniconda3:4.12.0 AS build
LABEL maintainer="Global Healthy Liveable City Indicator Study Collaboration Group"
LABEL url="https://github.com/global-healthy-liveable-cities/global-indicators"

COPY environment.yml .

ENV PATH=$PATH:/root/bin

RUN conda config --set show_channel_urls true \
    && conda config --set channel_priority strict \
    && conda config --prepend channels conda-forge \
    && conda update --yes -n base conda \
    && conda install -c conda-forge conda-pack \
    && conda env create -n env -f environment.yml \
    && conda pack -n env -o env.tar.gz \
    && conda list -n env --explicit > spec-file.txt

FROM alpine:3.18.4 AS runtime

COPY --from=build /env.tar.gz .
RUN mkdir /env \
    && tar xvzf /env.tar.gz -C /env \
    && rm -rv /env.tar.gz \
    && /env/bin/python /env/bin/conda-unpack \
    && adduser -u 8877 -D ghsci \
    && apk add --no-cache \
        gcc \
        g++ \
        git \
        osm2pgsql \
        osmctools

ENV PATH="/env/bin/:$PATH"
ENV PROJ_LIB="/env/share/proj"

RUN echo 'alias configure="python configure.py"' >> /etc/profile \
    && echo 'alias analysis="python analysis.py"' >> /etc/profile \
    && echo 'alias generate="python generate.py"' >> /etc/profile \
    && echo 'alias compare="python compare.py"' >> /etc/profile \
    && echo 'alias ghsci="python gui.py"' >> /etc/profile \
    && echo 'alias help="cat ../help.txt"' >> /etc/profile \
    && echo 'alias lab="printf \"\n$(tput bold)Jupyter Lab$(tput sgr0)\nOpen http://localhost:8888/lab to create or open a Notebook, e.g. example.ipynb\nTo shut down Jupyter Lab\n  - press Ctrl+C in this terminal window, or\n  - go to File > Shut Down in the Jupyter Lab interface.\n\n\" & jupyter lab --no-browser --notebook-dir=/home/ghsci/process --allow-root --config=/home/ghsci/jupyter_notebook_config.py"' >> /etc/profile \
    && echo 'export PS1="# "' >> /etc/profile

USER ghsci
WORKDIR /home/ghsci