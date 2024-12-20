FROM ubuntu:22.04

LABEL description="Tippecanoe and Tyler Too: incorporates additional dependencies for GIS data processing."

# Install dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    libprotobuf-dev \
    protobuf-compiler \
    libsqlite3-dev \
    zlib1g-dev \
    libcurl4-openssl-dev \
    git \
    wget \
    curl \
    make \
    postgresql-client # Facilitates communication with the Django Postgres database \
    gdal-bin # Facilitates GIS data processing \
    python3 \
    python3-pip \
    jq \
    netcat \
    tee \
    && rm -rf /var/lib/apt/lists/*

# Clone Tippecanoe and build
RUN git clone https://github.com/felt/tippecanoe.git /tippecanoe && \
    cd /tippecanoe && \
    make

# Set working directory
WORKDIR /tippecanoe

## In this directory, build the Docker image:
#sudo systemctl restart docker
#docker login
#docker build -t worldhistoricalgazetteer/tippecanoe .
#docker push worldhistoricalgazetteer/tippecanoe