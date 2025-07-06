#!/bin/bash

set -e # Ensure the script exits on error

cleanup() {
  echo "Cleaning up temporary directory: $REPO_DIR"
  if [ -d "$REPO_DIR" ]; then
    rm -rf "$REPO_DIR"
  fi
  unset CA_CERT CLIENT_CERT CLIENT_KEY minikube_ip
  if [ -d "/tmp/kubeconfig" ]; then
    shred -u /tmp/kubeconfig
  fi
}

# Register the cleanup function to be called on exit
trap cleanup EXIT

# Git repository details
REPO_URL="https://github.com/WorldHistoricalGazetteer/place.git"
REPO_DIR="/home/gazetteer/deployment-temp" # Temporary directory

# Create the temporary directory if necessary
mkdir -p "$REPO_DIR"

# Clone only the deploy/management directory (shallow clone)
git clone --depth 1 --filter=blob:none --sparse "$REPO_URL" "$REPO_DIR"
cd "$REPO_DIR"
git sparse-checkout init --cone
git sparse-checkout add deployment

if ! kubectl get secret kubeconfig -n management > /dev/null 2>&1; then

  # Base64-encode the certificates
  CA_CERT=$(base64 -w0 /home/gazetteer/.minikube/ca.crt)
  CLIENT_CERT=$(base64 -w0 /home/gazetteer/.minikube/profiles/minikube/client.crt)
  CLIENT_KEY=$(base64 -w0 /home/gazetteer/.minikube/profiles/minikube/client.key)

  # Get the Minikube IP
  minikube_ip=$(minikube ip)

  # Prepare kubeconfig
  cp /home/gazetteer/.kube/config /tmp/kubeconfig
  sed -i "s|certificate-authority: .*|certificate-authority-data: $CA_CERT|" /tmp/kubeconfig
  sed -i "s|client-certificate: .*|client-certificate-data: $CLIENT_CERT|" /tmp/kubeconfig
  sed -i "s|client-key: .*|client-key-data: $CLIENT_KEY|" /tmp/kubeconfig
  sed -i "s|server: https://127.0.0.1:[0-9]*|server: https://$minikube_ip:8443|" /tmp/kubeconfig

  # Create kubeconfig secret
  kubectl create secret generic kubeconfig \
    --from-file=config=/tmp/kubeconfig \
    -n management \
    --dry-run=client -o yaml | kubectl apply -f -

else
  echo "Secret 'kubeconfig' already exists in the 'management' namespace, skipping creation."
fi

# Check if the github-token secret already exists
if ! kubectl get secret github-token -n management > /dev/null 2>&1; then
  # Create a Secret for GitHub token
  kubectl create secret generic github-token \
    --from-literal=GITHUB_TOKEN="$GITHUB_TOKEN" \
    -n management \
    --dry-run=client -o yaml | kubectl apply -f -
else
  echo "Secret 'github-token' already exists in the 'management' namespace, skipping creation."
fi

# Install `deployment` Helm chart
helm upgrade --install management-chart "$REPO_DIR/deployment" \
  --namespace management \
  --create-namespace \
  --debug

echo "Deployment of management helm chart complete!"

# TODO: Continue with other Helm charts using the management pod's API endpoint