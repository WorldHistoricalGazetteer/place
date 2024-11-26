# Use the official PostGIS 15-3.4 image as a base
FROM postgis/postgis:15-3.4

# Install pgBackRest using apt-get
RUN apt-get update && \
    apt-get install -y pgbackrest

# Optional: Add pgBackRest config files to the container
# COPY pgbackrest.conf /etc/pgbackrest/

# Expose necessary ports (example for PostgreSQL)
EXPOSE 5432

# Set the entrypoint to run PostgreSQL as usual
ENTRYPOINT ["docker-entrypoint.sh"]

# Command to run PostgreSQL
CMD ["postgres"]

## In this directory, build the Docker image:
#docker login
#docker build -t worldhistoricalgazetteer/postgis-pgbackrest:15-3.4 .
#docker push worldhistoricalgazetteer/postgis-pgbackrest:15-3.4