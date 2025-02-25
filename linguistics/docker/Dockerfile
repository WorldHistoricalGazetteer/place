FROM python:3.11-slim-bullseye

LABEL maintainer="WHC @ Pitt"

# Set environment variables to reduce build noise
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONPATH=/usr/local/share/epitran

# Combine system package installation, Flite and CEDict installation, and cleanup into a single layer
RUN set -eux; \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        git curl unzip build-essential pkg-config libicu-dev && \
    pip install --no-binary=:pyicu: pyicu && \
    # Install Flite (required for English G2P in Epitran - see https://github.com/dmort27/epitran?tab=readme-ov-file#installation-of-flite-for-english-g2p)
    # Install Flite (required for English G2P in Epitran)
    cd /tmp && git clone https://github.com/festvox/flite.git && \
    cd flite && ./configure && make -j$(nproc) && make install && \
    cd testsuite && make lex_lookup && cp lex_lookup /usr/local/bin && \
    # Download the CC-CEDict dictionary for Chinese G2P in Epitran
    mkdir -p $PYTHONPATH && \
    curl -L -o $PYTHONPATH/cedict.zip https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.zip && \
    unzip $PYTHONPATH/cedict.zip -d $PYTHONPATH && \
    rm $PYTHONPATH/cedict.zip && \
    # Cleanup
    apt-get purge -y --auto-remove && \
    rm -rf /var/lib/apt/lists/* /tmp/*

# Copy the other dictionaries into the Epitran share directory \
COPY iso639.py $PYTHONPATH/iso639.py
COPY iso15924.py $PYTHONPATH/iso15924.py

WORKDIR /app

# Install dependencies and set correct permissions
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Install Epitran from the forked git repository
RUN pip install --no-cache-dir --upgrade --force-reinstall git+https://github.com/WorldHistoricalGazetteer/epitran.git

# Expose the HTTP server port
EXPOSE 8000

# Copy the main server script (may be updated from git repository at runtime)
COPY server.py /app/

# Start the linguistics server
CMD ["python", "/app/server.py"]

## In the project root, build the Docker image:
#sudo systemctl restart docker
#docker login
#docker build -t worldhistoricalgazetteer/linguistics:0.0.1 ./linguistics/docker
#docker push worldhistoricalgazetteer/linguistics:0.0.1