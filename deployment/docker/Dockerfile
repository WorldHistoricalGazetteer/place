FROM python:3.11-slim-bullseye

LABEL maintainer="WHC @ Pitt"

WORKDIR /app

# Install Helm, Kubectl, Git, jq, yq, base64, and zip
RUN apt-get update && apt-get install -y curl gnupg git jq wget zip && \
    curl https://baltocdn.com/helm/signing.asc | gpg --dearmor | tee /usr/share/keyrings/helm.gpg > /dev/null && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/helm.gpg] https://baltocdn.com/helm/stable/debian/ all main" | tee /etc/apt/sources.list.d/helm-stable-debian.list && \
    apt-get update && apt-get install -y helm && \
    curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && \
    install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl && \
    wget https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O /usr/local/bin/yq && \
    chmod +x /usr/local/bin/yq && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]

## In the project root, build the Docker image:
#sudo systemctl restart docker
#docker login
#docker build -t worldhistoricalgazetteer/deployment:0.0.2 ./deployment/docker
#docker push worldhistoricalgazetteer/deployment:0.0.2