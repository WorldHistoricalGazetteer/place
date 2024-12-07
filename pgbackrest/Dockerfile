# Use the official PostGIS 15-3.4 image as a base
FROM postgis/postgis:15-3.4

# Install pgBackRest using apt-get
RUN apt-get update && \
    apt-get install -y nano rsync pgbackrest && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

## In this directory, build the Docker image:
#docker login
#docker build -t worldhistoricalgazetteer/postgis-pgbackrest:15-3.4 .
#docker push worldhistoricalgazetteer/postgis-pgbackrest:15-3.4