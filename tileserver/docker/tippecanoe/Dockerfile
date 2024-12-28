FROM ubuntu:22.04

LABEL description="Wat Tyler: incorporates Tippecanoe and additional dependencies for debugging."

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
    netcat \
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