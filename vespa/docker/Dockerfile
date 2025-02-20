FROM python:3.10.7-slim-bullseye

LABEL maintainer="WHC @ Pitt"

# Combine system package installation, Vespa tool installation, and cleanup into a single layer
RUN set -eux; \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        python3-gdal \
        libpq-dev \
        curl \
        rsync \
        file \
        gpgv \
        lsb-release \
        sudo \
        nano \
        locate \
        netcat-openbsd \
        procps \
        psmisc \
        git \
        unzip \
        tar \
        aria2 && \
    # Install vespa-cli
    mkdir -p /usr/local/vespa && \
    curl -L -o /usr/local/vespa/vespa-cli.tar.gz https://github.com/vespa-engine/vespa/releases/download/v8.460.16/vespa-cli_8.460.16_linux_amd64.tar.gz && \
    tar -xzf /usr/local/vespa/vespa-cli.tar.gz -C /usr/local/vespa && \
    mv /usr/local/vespa/vespa-cli_* /usr/local/vespa/vespa-cli && \
    rm /usr/local/vespa/vespa-cli.tar.gz && \
    chmod +x /usr/local/vespa/vespa-cli && \
    ln -s /usr/local/vespa/vespa-cli /usr/local/bin/vespa-cli && \
    # Cleanup
    apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /code

# Install dependencies and set correct permissions
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copy application code
COPY ./api /code/api

# Container will need to run as root user (0) to enable Vespa CLI to create required directories
# These include /.vespa and /.cache, perhaps others too
USER 0:0

# Add Vespa CLI to the PATH
ENV PATH="/usr/local/vespa/vespa-cli/bin:${PATH}"

# Set the default port and run the FastAPI server
ENV PORT=8082
CMD ["sh", "-c", "fastapi run api/main.py --port ${PORT}"]

## In the project root, build the Docker image:
#sudo systemctl restart docker
#docker login
#docker build -t worldhistoricalgazetteer/vespa-api:0.0.11 ./vespa/docker
#docker push worldhistoricalgazetteer/vespa-api:0.0.11