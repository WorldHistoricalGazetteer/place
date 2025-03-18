#!/bin/bash

set -e

# Git repository details
REPO_URL="https://github.com/WorldHistoricalGazetteer/place.git"
REPO_DIR="/home/gazetteer/deployment-temp" # Temporary directory

# Create the temporary directory if necessary
mkdir -p "$REPO_DIR"

# Clone only the deploy/management directory (shallow clone)
git clone --depth 1 --filter=blob:none --sparse "$REPO_URL" "$REPO_DIR"
cd "$REPO_DIR"
git sparse-checkout init --cone
git sparse-checkout add deploy/management

# Prepare values
CA_CERT=$(base64 -w0 /home/gazetteer/.minikube/ca.crt)
CLIENT_CERT=$(base64 -w0 /home/gazetteer/.minikube/profiles/minikube/client.crt)
CLIENT_KEY=$(base64 -w0 /home/gazetteer/.minikube/profiles/minikube/client.key)
minikube_ip=$(minikube ip)

# Install Helm chart
helm upgrade --install management-chart "deploy/management" \
  --namespace management \
  --create-namespace \
  --set hcpClientId="$HCP_CLIENT_ID" \
  --set hcpClientSecret="$HCP_CLIENT_SECRET" \
  --set minikubeIp="$minikube_ip" \
  --set caCert="$CA_CERT" \
  --set clientCert="$CLIENT_CERT" \
  --set clientKey="$CLIENT_KEY"

unset CA_CERT CLIENT_CERT CLIENT_KEY minikube_ip

# Clean up temporary clone
cd ..
rm -rf "$REPO_DIR"