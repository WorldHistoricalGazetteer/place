# --- Builder stage: Install tools, build python deps ---
FROM python:3.11-slim-bullseye AS builder

LABEL maintainer="ISHI @ Pitt"

WORKDIR /app

# Set Helm version to match the Server Version reported by `helm version` on the host
ARG HELM_VERSION=3.15.4

# Set kubectl version to match the Server Version reported by `kubectl version` on the host
ARG KUBECTL_VERSION=1.32.0

# Set yq version
ARG YQ_VERSION=4.47.1

# Install build tools and dependencies for downloading binaries
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      bash curl gnupg git jq wget zip rsync iputils-ping dnsutils build-essential && \
    # Install Helm pinned to version
    curl -L https://get.helm.sh/helm-v${HELM_VERSION}-linux-amd64.tar.gz -o helm.tar.gz && \
    tar -zxvf helm.tar.gz && \
    mv linux-amd64/helm /usr/local/bin/helm && \
    chmod +x /usr/local/bin/helm && \
    rm -rf linux-amd64 helm.tar.gz && \
    # Install kubectl pinned to version
    curl -LO "https://dl.k8s.io/release/v${KUBECTL_VERSION}/bin/linux/amd64/kubectl" && \
    install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl && \
    # Install yq
    wget https://github.com/mikefarah/yq/releases/download/v${YQ_VERSION}/yq_linux_amd64 -O /usr/local/bin/yq && \
    chmod +x /usr/local/bin/yq && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

# --- Final stage: minimal runtime image ---
FROM python:3.11-slim-bullseye

LABEL maintainer="ISHI @ Pitt"

WORKDIR /app

# Install runtime dependencies (bash, curl, git, jq, wget, zip)
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash curl git jq wget zip iputils-ping dnsutils && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Create a writable location for virtualenv
RUN mkdir -p /venv && chmod 777 /venv

# Copy Helm, kubectl, yq from builder
COPY --from=builder /usr/local/bin/helm /usr/local/bin/helm
COPY --from=builder /usr/local/bin/kubectl /usr/local/bin/kubectl
COPY --from=builder /usr/local/bin/yq /usr/local/bin/yq

# Copy installed Python packages from builder to final image
COPY --from=builder /install /usr/local

COPY . .

# Default command can be overridden, making it optional for cron or other usage
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]

## In the project root, build the Docker image:
#sudo systemctl restart docker
#docker login
#docker build -t worldhistoricalgazetteer/deployment:0.0.3 ./deployment/docker
#docker push worldhistoricalgazetteer/deployment:0.0.3