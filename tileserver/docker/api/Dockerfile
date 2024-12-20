FROM python:3.9
WORKDIR /code
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt
COPY ./api /code/api
RUN chown -R 999:999 /code
USER 999:999
ENV PORT=8081
CMD ["sh", "-c", "fastapi run api/main.py --port ${PORT}"]

## In the project root, build the Docker image:
#sudo systemctl restart docker
#docker login
#docker build -t worldhistoricalgazetteer/tileapi ./tileserver/docker/api
#docker push worldhistoricalgazetteer/tileapi:0.0.1