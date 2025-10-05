#!/bin/bash
set -euo pipefail

# This would normally be called on the Pitt VM via:
# bash <(curl -s "https://raw.githubusercontent.com/WorldHistoricalGazetteer/place/main/deployment/deploy.sh")

REPO_DIR="$HOME/deployment-repo"
REPO_URL="https://github.com/WorldHistoricalGazetteer/place.git"
BRANCH="main"

if [ ! -d "$REPO_DIR/.git" ]; then
  echo "Cloning WHG repository (sparse checkout of deployment/)..."
  rm -rf "$REPO_DIR"
  mkdir -p "$REPO_DIR"
  git clone --filter=blob:none --no-checkout "$REPO_URL" "$REPO_DIR"
  cd "$REPO_DIR"
  git sparse-checkout init --cone
  git sparse-checkout set deployment
  git checkout "$BRANCH"
else
  echo "Updating WHG repository (sparse checkout)..."
  cd "$REPO_DIR"
  git fetch origin
  git reset --hard "origin/$BRANCH"
fi

cleanup() {
  unset CA_CERT CLIENT_CERT CLIENT_KEY minikube_ip
  if [ -d "/tmp/kubeconfig" ]; then
    shred -u /tmp/kubeconfig
  fi
}

# Register the cleanup function to be called on exit
trap cleanup EXIT

if ! kubectl get namespace management >/dev/null 2>&1; then
  echo "Creating 'management' namespace..."
  kubectl create namespace management
else
  echo "'management' namespace already exists."
fi

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
  --dry-run=client -o yaml | \
  kubectl label -f - --local app.kubernetes.io/managed-by=Helm -o yaml | \
  kubectl annotate -f - --local \
    meta.helm.sh/release-name=management-chart \
    meta.helm.sh/release-namespace=management -o yaml | \
  kubectl apply -f -

else
  echo "Secret 'kubeconfig' already exists in the 'management' namespace, skipping creation."
fi

# Check if the github-token secret already exists
if ! kubectl get secret github-token -n management > /dev/null 2>&1; then
  # Create a Secret for GitHub token
  kubectl create secret generic github-token \
  --from-literal=GITHUB_TOKEN="$GITHUB_TOKEN" \
  -n management \
  --dry-run=client -o yaml | \
  kubectl label -f - --local app.kubernetes.io/managed-by=Helm -o yaml | \
  kubectl annotate -f - --local \
    meta.helm.sh/release-name=management-chart \
    meta.helm.sh/release-namespace=management -o yaml | \
  kubectl apply -f -
else
  echo "Secret 'github-token' already exists in the 'management' namespace, skipping creation."
fi

if ! kubectl get secret whg-secret -n management > /dev/null 2>&1; then
  # Fetch remote secrets and create Kubernetes secrets
  source "$REPO_DIR/deployment/load-secrets.sh"
fi

# Apply consistent labels by node name pattern
echo "Applying node labels from values.yaml..."
NODE_CONFIG_FILE="$REPO_DIR/deployment/values.yaml"

if yq e '.nodes' "$NODE_CONFIG_FILE" >/dev/null; then
  nodes=$(yq e '.nodes | keys | .[]' "$NODE_CONFIG_FILE")

  for node in $nodes; do
    echo "Processing node: $node"

    # Get labels as separate key=value strings
    labels=$(yq e ".nodes.\"$node\" | to_entries | .[] | \"\(.key)=\(.value)\"" "$NODE_CONFIG_FILE")

    for label in $labels; do
      echo "  Applying label $label to $node"
      kubectl label --overwrite "node/$node" $label
    done
  done
else
  echo "No 'nodes' section found in values.yaml; skipping node labeling."
fi

echo "Node labelling complete!"

# Install `deployment` Helm chart
helm upgrade --install management-chart "$REPO_DIR/deployment" \
  --namespace management \
  --create-namespace \
  --debug

echo "Deployment of management helm chart complete!"
