 ##############################################################################
# Build an image from the dockerfile:
# >>> docker build . -t globalhealthyliveablecities/global-indicators:latest
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

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
ENV UV_PYTHON_DOWNLOADS=0

WORKDIR /home/ghsci

COPY ./pyproject.toml /home/ghsci/pyproject.toml

RUN apt-get update && apt-get install -y build-essential gdal-bin libgdal-dev
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=/pyproject.toml,target=/pyproject.toml \
    uv sync --no-install-project --no-dev

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# =============================================================================
# Runtime environment
FROM python:3.12-slim-bookworm

RUN useradd --create-home ghsci

# create /app directory and chown to to node user or else it will be owned by root
RUN mkdir -p /home/ghsci && chown ghsci:ghsci /home/ghsci
WORKDIR /home/ghsci


LABEL maintainer="Global Observatory of Healthy and Sustainable Cities"
LABEL url="https://github.com/healthysustainablecities/global-indicators"
LABEL description="Docker image for the Global Healthy and Sustainable City Indicators software. This image provides a Python environment with all necessary dependencies to run the GHSCI analysis and reporting tools."

# Copy the application from the builder
COPY --from=builder --chown=ghsci:home/ghsci /home/ghsci /home/ghsci

RUN apt-get update && apt-get install -y gcc g++ git osm2pgsql osmctools && \
    # clean up cache
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

ENV PATH="/env/bin/:$PATH"
ENV PROJ_LIB="/env/share/proj"

RUN echo 'alias configure="python configure.py"' >> ~/.bashrc && \
    echo 'alias analysis="python analysis.py"' >> ~/.bashrc && \
    echo 'alias generate="python generate.py"' >> ~/.bashrc && \
    echo 'alias compare="python compare.py"' >> ~/.bashrc  && \
    echo 'alias ghsci="python gui.py"' >> ~/.bashrc && \
    echo 'alias help="cat ../help.txt"' >> ~/.bashrc && \
    echo 'alias lab="printf \"\n$(tput bold)Jupyter Lab$(tput sgr0)\nOpen http://localhost:8888/lab to create or open a Notebook, e.g. example.ipynb\nTo shut down Jupyter Lab\n  - press Ctrl+C in this terminal window, or\n  - go to File > Shut Down in the Jupyter Lab interface.\n\n\" & jupyter lab --no-browser --notebook-dir=/app/process --allow-root --config=/app/jupyter_notebook_config.py"' >> ~/.bashrc && \
    echo 'export PS1="# "' >> ~/.bashrc

USER ghsci
