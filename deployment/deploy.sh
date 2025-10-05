#!/bin/bash
set -euo pipefail

# =========================================
# WHG Deployment Script for Minikube
# =========================================
# This would normally be called on the Pitt VM via:
# bash <(curl -s "https://raw.githubusercontent.com/WorldHistoricalGazetteer/place/main/deployment/deploy.sh")

REPO_DIR="$HOME/deployment-repo"
REPO_URL="https://github.com/WorldHistoricalGazetteer/place.git"
BRANCH="main"
KPROXY_PORT=8001
MINIKUBE_PROFILE="minikube"
MINIKUBE_NODES=4
MINIKUBE_CPUS=2
MINIKUBE_MEMORY=6144
MINIKUBE_DISK="8g"
HOST_MOUNT="/ix1/whcdh:/minikube-whcdh"

# -----------------------------------------
# Start Minikube if not running
# -----------------------------------------
if minikube status -p "$MINIKUBE_PROFILE" &>/dev/null; then
  MINIKUBE_STATUS=$(minikube status -p "$MINIKUBE_PROFILE" -o json | jq -r '.[0].Host // "Stopped"' 2>/dev/null || echo "Stopped")
else
  MINIKUBE_STATUS="Stopped"
fi

if [ "$MINIKUBE_STATUS" != "Running" ]; then
  echo "Starting Minikube with $MINIKUBE_NODES nodes..."
  minikube start \
    -p "$MINIKUBE_PROFILE" \
    --nodes="$MINIKUBE_NODES" \
    --driver=podman \
    --container-runtime=containerd \
    --cpus="$MINIKUBE_CPUS" \
    --memory="$MINIKUBE_MEMORY" \
    --disk-size="$MINIKUBE_DISK" \
    --mount-string="$HOST_MOUNT" \
    --mount
else
  echo "✅ Minikube already running."
fi

# -----------------------------------------
# Wait until all nodes are Ready
# -----------------------------------------
echo "Waiting for all Minikube nodes to be Ready..."
until kubectl get nodes | grep -q "Ready"; do
  echo "Waiting for nodes..."
  sleep 5
done
echo "All nodes Ready."

# -----------------------------------------
# Clone or update the WHG repository
# -----------------------------------------
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

# -----------------------------------------
# Cleanup function for sensitive files
# -----------------------------------------
cleanup() {
  unset CA_CERT CLIENT_CERT CLIENT_KEY minikube_ip
  [ -d "/tmp/kubeconfig" ] && shred -u /tmp/kubeconfig
}
trap cleanup EXIT

# -----------------------------------------
# Ensure 'whg' namespace exists
# -----------------------------------------
if ! kubectl get namespace whg >/dev/null 2>&1; then
  echo "Creating 'whg' namespace..."
  kubectl create namespace whg
else
  echo "'whg' namespace already exists."
fi

# -----------------------------------------
# Configure metalLB if not already configured
# -----------------------------------------

# Get the Minikube IP and derive a reasonable IP range
MINIKUBE_IP=$(minikube ip)
SUBNET_PREFIX=$(echo "$MINIKUBE_IP" | awk -F. '{print $1"."$2"."$3}')
METALLB_RANGE_START="${SUBNET_PREFIX}.200"
METALLB_RANGE_END="${SUBNET_PREFIX}.250"
METALLB_NAMESPACE="metallb-system"

echo "Configuring MetalLB address pool..."
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  namespace: $METALLB_NAMESPACE
  name: config
data:
  config: |
    address-pools:
    - name: default
      protocol: layer2
      addresses:
      - ${METALLB_RANGE_START}-${METALLB_RANGE_END}
EOF

echo "✅ MetalLB ConfigMap applied/updated."

# -----------------------------------------
# Enable Minikube addons idempotently
# -----------------------------------------
echo "Enabling required Minikube addons..."
for addon in dashboard metrics-server metallb; do
    minikube addons enable "$addon"
done

# -----------------------------------------
# Start kubectl proxy if not already running
# -----------------------------------------
if ! lsof -iTCP:$KPROXY_PORT -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Starting kubectl proxy on port $KPROXY_PORT..."
  nohup kubectl proxy --address=0.0.0.0 --port=$KPROXY_PORT --disable-filter=true \
    > "$HOME/kubectl_proxy.log" 2>&1 &
else
  echo "kubectl proxy already running on port $KPROXY_PORT"
fi

echo "To access the Kubernetes dashboard from your local machine:"
echo "  ssh -L 8010:127.0.0.1:$KPROXY_PORT <username>@gazetteer.crcd.pitt.edu"
echo "Then visit:"
echo "  http://localhost:8010/api/v1/namespaces/kubernetes-dashboard/services/http:kubernetes-dashboard:/proxy/#/workloads?namespace=_all"

# -----------------------------------------
# Create kubeconfig secret if missing
# -----------------------------------------
if ! kubectl get secret kubeconfig -n whg >/dev/null 2>&1; then
  echo "Creating kubeconfig secret..."
  CA_CERT=$(base64 -w0 /home/gazetteer/.minikube/ca.crt)
  CLIENT_CERT=$(base64 -w0 /home/gazetteer/.minikube/profiles/minikube/client.crt)
  CLIENT_KEY=$(base64 -w0 /home/gazetteer/.minikube/profiles/minikube/client.key)
  minikube_ip=$(minikube ip)

  cp /home/gazetteer/.kube/config /tmp/kubeconfig
  sed -i "s|certificate-authority: .*|certificate-authority-data: $CA_CERT|" /tmp/kubeconfig
  sed -i "s|client-certificate: .*|client-certificate-data: $CLIENT_CERT|" /tmp/kubeconfig
  sed -i "s|client-key: .*|client-key-data: $CLIENT_KEY|" /tmp/kubeconfig
  sed -i "s|server: https://127.0.0.1:[0-9]*|server: https://$minikube_ip:8443|" /tmp/kubeconfig

  kubectl create secret generic kubeconfig \
    --from-file=config=/tmp/kubeconfig \
    -n whg \
    --dry-run=client -o yaml | \
  kubectl label -f - --local app.kubernetes.io/managed-by=Helm -o yaml | \
  kubectl annotate -f - --local \
    meta.helm.sh/release-name=management-chart \
    meta.helm.sh/release-namespace=whg -o yaml | \
  kubectl apply -f -
else
  echo "Secret 'kubeconfig' already exists."
fi

# -----------------------------------------
# Create GitHub token secret if missing
# -----------------------------------------
if ! kubectl get secret github-token -n whg >/dev/null 2>&1; then
  echo "Creating github-token secret..."
  kubectl create secret generic github-token \
    --from-literal=GITHUB_TOKEN="$GITHUB_TOKEN" \
    -n whg \
    --dry-run=client -o yaml | \
  kubectl label -f - --local app.kubernetes.io/managed-by=Helm -o yaml | \
  kubectl annotate -f - --local \
    meta.helm.sh/release-name=management-chart \
    meta.helm.sh/release-namespace=whg -o yaml | \
  kubectl apply -f -
else
  echo "Secret 'github-token' already exists."
fi

# -----------------------------------------
# Load remote WHG secrets if needed
# -----------------------------------------
if ! kubectl get secret whg-secret -n whg >/dev/null 2>&1; then
  echo "Fetching and creating 'whg-secret'..."
  source "$REPO_DIR/deployment/load-secrets.sh"
else
  echo "Secret 'whg-secret' already exists."
fi

# -----------------------------------------
# Apply consistent node labels from values.yaml
# -----------------------------------------
echo "Applying node labels from values.yaml..."
NODE_CONFIG_FILE="$REPO_DIR/deployment/values.yaml"

if yq e '.nodes' "$NODE_CONFIG_FILE" >/dev/null; then
  nodes=$(yq e '.nodes | keys | .[]' "$NODE_CONFIG_FILE")
  for node in $nodes; do
    echo "Processing node: $node"
    labels=$(yq e ".nodes.\"$node\" | to_entries | .[] | \"\(.key)=\(.value)\"" "$NODE_CONFIG_FILE")
    for label in $labels; do
      echo "  Applying label $label to $node"
      kubectl label --overwrite "node/$node" $label
    done
  done
else
  echo "No 'nodes' section found in values.yaml; skipping node labeling."
fi

# -----------------------------------------
# Install/upgrade the management Helm chart
# -----------------------------------------
echo "Deploying Helm chart..."
helm upgrade --install management-chart "$REPO_DIR/deployment" \
  --namespace whg \
  --create-namespace \
  --debug

echo "WHG deployment complete!"
