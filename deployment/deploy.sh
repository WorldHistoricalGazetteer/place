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

# Install `deployment` Helm chart
helm upgrade --install management-chart "$REPO_DIR/deployment" \
  --namespace management \
  --create-namespace \
  --debug

echo "Deployment of management helm chart complete!"

# TODO: Continue with other Helm charts using the management pod's API endpoint - See Issue #59

exit 99 # Exit with a non-zero code to indicate success

######################
# ORIGINAL deploy.sh #
######################

#### Prepare the environment ####

# Set logging
export LOG_FILE="/var/log/kubernetes-setup.log"
exec > >(tee -i $LOG_FILE) 2>&1

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run this script as root or with sudo."
    exit 1
fi

# Identify the absolute path of this script's directory; load helper functions
SCRIPT_DIR="$(realpath "$(dirname "${BASH_SOURCE[0]}")")"
export SCRIPT_DIR
source "$SCRIPT_DIR/functions.sh"

# Identify the Kubernetes environment, set variables
identify_environment
export KUBECONFIG=/etc/kubernetes/admin.conf

# Remove any previous Kubernetes installation
remove_kubernetes

#### Install required packages and configure the system ####

# Load environment variables from .env file
set -a
source ./.env
set +a

# Add Docker GPG key
echo "Adding Docker GPG key..."
if curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --yes --dearmor -o /etc/apt/trusted.gpg.d/docker.gpg; then
    echo "Docker GPG key added successfully."
else
    echo "Failed to add Docker GPG key."
    exit 1
fi

# Add Docker repository with the signed-by option
echo "Adding Docker repository..."
echo "deb [arch=amd64 signed-by=/etc/apt/trusted.gpg.d/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

# Add Kubernetes GPG key
echo "Adding Kubernetes GPG key..."
if curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.30/deb/Release.key | gpg --yes --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg; then
    echo "Kubernetes GPG key added successfully."
else
    echo "Failed to add Kubernetes GPG key."
    exit 1
fi

# Add Kubernetes repository with the signed-by option
echo "Adding Kubernetes repository..."
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.30/deb/ /" | tee /etc/apt/sources.list.d/kubernetes.list > /dev/null

# Update packages
echo "Updating system package indices..."
if ! apt-get update -qy; then
    echo "Error: Failed to update package list. Exiting."
    exit 1
fi

# Install/update packages listed in requirements.txt
while IFS= read -r line; do
    # Skip empty lines or comment lines (those starting with #)
    [[ "$line" =~ ^\s*$ || "$line" =~ ^\s*# ]] && continue

    # Use awk to split package and version based on '==' delimiter
    PACKAGE=$(echo "$line" | awk -F '==' '{print $1}')
    VERSION=$(echo "$line" | awk -F '==' '{print $2}')

    if [[ -n "$PACKAGE" && "$PACKAGE" != \#* ]]; then
        # Check if the package is installed and matches the required version
        INSTALLED_VERSION=$(dpkg-query -W -f='${Version}' "$PACKAGE" 2>/dev/null)
        if [[ "$INSTALLED_VERSION" != "$VERSION" ]]; then
            echo "Attempting to install or update $PACKAGE to version $VERSION..."

            # Try installing the specified version first
            if ! apt-get install -qy "$PACKAGE=$VERSION" --allow-downgrades --allow-change-held-packages; then
                echo "Version $VERSION not available, trying the closest compatible version..."

                # Install the latest available version if the specified version isn't found
                if ! apt-get install -qy "$PACKAGE" --allow-downgrades --allow-change-held-packages; then
                    echo "Error: Failed to install $PACKAGE. Exiting."
                    exit 1
                fi

                # If we installed a different version, issue a warning
                NEW_INSTALLED_VERSION=$(dpkg-query -W -f='${Version}' "$PACKAGE" 2>/dev/null)
                echo "WARNING: Installed a compatible version of $PACKAGE: $NEW_INSTALLED_VERSION instead of $VERSION."
            fi
        else
            echo "$PACKAGE is already at the required version ($INSTALLED_VERSION)."
        fi
    fi
done < requirements.txt

# Hold the Kubernetes packages to prevent automatic upgrades
apt-mark hold kubelet kubeadm kubectl

# Configure containerd
containerd --version
echo "Creating/updating containerd configuration..."
mkdir -p /etc/containerd
cp "$SCRIPT_DIR/system/containerd-config.toml" /etc/containerd/config.toml
touch /etc/containerd/debug.toml

# Check that sandbox_image exists in the containerd config file
if grep -q '^[[:space:]]*sandbox_image' "$SCRIPT_DIR/system/containerd-config.toml"; then
    # If it exists, update it
    sed -i "s|^sandbox_image = .*|sandbox_image = '$PAUSE_IMAGE'|" "$SCRIPT_DIR/system/containerd-config.toml"
else
    echo "sandbox_image configuration missing in $SCRIPT_DIR/system/containerd-config.toml."
    exit 1
fi

# Restart and validate containerd
if systemctl restart containerd; then
    echo "Containerd is running."
else
    echo "Error: Failed to restart containerd. Exiting."
    exit 1
fi
echo "Validating containerd setup..."
if ctr version; then
    echo "Containerd setup validated successfully."
else
    echo "Error: Containerd validation failed. Exiting."
    exit 1
fi

wget -O /usr/local/bin/yq https://github.com/mikefarah/yq/releases/download/v4.13.0/yq_linux_amd64
if [ $? -ne 0 ]; then
    echo "Error occurred while downloading yq."
    exit 1
fi
chmod +x /usr/local/bin/yq

# Load configuration from YAML files
HELM_VERSION=$(yq eval '.helm.version' "$SCRIPT_DIR/system/helm-config.yaml")
HELM_REPO_URL=$(yq eval '.helm.repo_url' "$SCRIPT_DIR/system/helm-config.yaml")
VESPA_VERSION=$(yq eval '.vespa.version' "$SCRIPT_DIR/system/vespa-config.yaml")
VESPA_DOWNLOAD_URL=$(yq eval '.vespa.download_url' "$SCRIPT_DIR/system/vespa-config.yaml")

# Install Helm
echo "Installing Helm version $HELM_VERSION..."
curl -fsSL "$HELM_REPO_URL/helm-v$HELM_VERSION-linux-amd64.tar.gz" -o helm.tar.gz
if [ $? -ne 0 ]; then
    echo "Error occurred while downloading Helm."
    exit 1
fi
tar -zxvf helm.tar.gz
mv linux-amd64/helm /usr/local/bin/helm
rm -rf linux-amd64 helm.tar.gz
helm version
if [ $? -ne 0 ]; then
    echo "Error occurred while checking Helm version."
    exit 1
fi

# Disable swap
echo "Disabling swap..."
swapoff -a
cp /etc/fstab /etc/fstab.bak
sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab
echo "Swap disabled successfully."

# Configure IP Tables
echo "Configuring IP Tables..."
iptables -F # Flush all rules
iptables -X # Delete all chains
iptables -A INPUT -i lo -j ACCEPT # Allow loopback interface
iptables -A OUTPUT -o lo -j ACCEPT # Allow loopback interface
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT # Allow established connections
iptables -A INPUT -p tcp --dport 22 -j ACCEPT # Allow SSH
iptables -A INPUT -p tcp --dport 80 -j ACCEPT # Allow HTTP
iptables -A INPUT -p tcp --dport 443 -j ACCEPT # Allow HTTPS
iptables -A INPUT -p icmp -j ACCEPT # Allow ICMP
iptables -A INPUT -p tcp --dport 10250 -j ACCEPT # Allow Kubelet API
if [ "$K8S_CONTROLLER" == 1 ]; then
  # Control Plane Node
  iptables -A INPUT -p tcp --dport 6443 -j ACCEPT # Allow Kubernetes API server
  iptables -A INPUT -p tcp --dport 2379:2380 -j ACCEPT # Allow etcd server client API
  iptables -A INPUT -p tcp --dport 10251 -j ACCEPT # Allow kube-scheduler
  iptables -A INPUT -p tcp --dport 10252 -j ACCEPT # Allow kube-controller-manager
fi
if [[ "$K8S_ENVIRONMENT" == "development" || "$K8S_ENVIRONMENT" == "staging" ]]; then
  # Worker Node
  iptables -A INPUT -p tcp --dport 30000:32767 -j ACCEPT # Allow NodePort Services
fi

# Install Vespa CLI
echo "Installing Vespa CLI version $VESPA_VERSION..."
curl -LO $VESPA_DOWNLOAD_URL
if [ $? -ne 0 ]; then
    echo "Error occurred while downloading Vespa CLI."
    exit 1
fi
tar -xvf vespa-cli_${VESPA_VERSION}_linux_amd64.tar.gz
mv vespa-cli_${VESPA_VERSION}_linux_amd64/bin/vespa /usr/local/bin/
rm -rf vespa-cli_${VESPA_VERSION}_linux_amd64 vespa-cli_${VESPA_VERSION}_linux_amd64.tar.gz
vespa version || { echo "Vespa CLI installation failed"; exit 1; }

#### Install Kubernetes components ####

# Override kubelet configuration
# The webhook flags are specified in documentation for `kube-prometheus`
echo "Overriding kubelet configuration..."
OVERRIDE_FILE="/etc/systemd/system/kubelet.service.d/override.conf"
mkdir -p $(dirname $OVERRIDE_FILE)
tee $OVERRIDE_FILE > /dev/null <<EOF
[Service]
Environment="KUBELET_EXTRA_ARGS=--cgroup-driver=systemd --pod-infra-container-image=$PAUSE_IMAGE --authentication-token-webhook=true --authorization-mode=Webhook"
EOF
systemctl daemon-reload

if [ "$K8S_CONTROLLER" == 1 ]; then

  # Initialize Kubernetes cluster
  echo "Initializing Kubernetes cluster with pod network CIDR $POD_NETWORK_CIDR..."
  kubeadm config images pull
  kubeadm init -v=9 --pod-network-cidr="$POD_NETWORK_CIDR"
  if [ $? -ne 0 ]; then
      echo "Error occurred during Kubernetes cluster initialization."
      exit 1
  fi
  wait_for_k8s # Wait for the Kubernetes control-plane to be ready

else

  # Ensure JOIN_COMMAND is passed as an argument
  if [ -z "$JOIN_COMMAND" ]; then
      echo "Error: JOIN_COMMAND must be provided to join the worker node."
      exit 1
  fi

  # Join the worker node to the Kubernetes cluster
  echo "Joining the worker node to the Kubernetes cluster using the provided join command..."
  kubeadm join $JOIN_COMMAND
  if [ $? -ne 0 ]; then
      echo "Error occurred while joining the worker node to the Kubernetes cluster."
      exit 1
  fi

fi

# Get the current node name based on the node's internal IP
NODE_INTERNAL_IP=$(hostname -I | awk '{print $1}')
NODE_NAME=$(kubectl get nodes -o json | jq -r ".items[] | select(.status.addresses[] | select(.type==\"InternalIP\" and .address==\"$NODE_INTERNAL_IP\")) | .metadata.name")
if [[ -z "$NODE_NAME" ]]; then
  echo "Error: Unable to determine the current node name based on InternalIP ($NODE_INTERNAL_IP)."
  exit 1
fi
export NODE_NAME

# Label the node based on K8S_CONTROLLER, K8S_ROLE, and K8S_ENVIRONMENT; always allow pods on a control plane node
kubectl label node "$NODE_NAME" controller=$K8S_CONTROLLER role=$K8S_ROLE environment=$K8S_ENVIRONMENT

# If the node is a controller and not a backup, add the vespa-role-admin label
if [[ "$K8S_ROLE" != "backup" && "$K8S_CONTROLLER" == "1" ]]; then
  kubectl label node "$NODE_NAME" vespa-role-admin=true
  kubectl label node "$NODE_NAME" whg-site=true
  kubectl label node "$NODE_NAME" tileserver=true
  kubectl label node "$NODE_NAME" monitoring=true
fi

# If the node is not a backup, add the vespa-role-container and vespa-role-content labels
if [[ "$K8S_ROLE" != "backup" ]]; then
  kubectl label node "$NODE_NAME" vespa-role-container=true
  kubectl label node "$NODE_NAME" vespa-role-content=true
fi
kubectl taint nodes --all node-role.kubernetes.io/control-plane-

# Install Flannel (CNI = Container Network Interface) for Kubernetes
echo "Installing Flannel for Kubernetes..."
helm install flannel ./flannel -n kube-system
echo "Waiting for Flannel network pods to be ready..."
kubectl rollout status daemonset/kube-flannel-ds -n kube-system

# Copy the kubeconfig file to the user's home directory and to the root user
echo "Copying kubeconfig file to the user's home directory..."
USER_HOME="/home/$SUDO_USER"
mkdir -p "$USER_HOME/.kube"
cp -f /etc/kubernetes/admin.conf "$USER_HOME/.kube/config"
chown $SUDO_USER:$SUDO_USER "$USER_HOME/.kube/config"
echo "Copying kubeconfig file to the root user's home directory..."
mkdir -p /root/.kube
cp -f /etc/kubernetes/admin.conf /root/.kube/config
chown root:root /root/.kube/config

# Check if kubectl was installed correctly
kubectl version --client
if [ $? -ne 0 ]; then
    echo "Error occurred while checking Kubernetes version."
    exit 1
fi

# Verify that kubectl can access the cluster
kubectl get nodes
kubectl get pods -n kube-system
if [ $? -ne 0 ]; then
    echo "Error occurred while configuring kubectl."
    exit 1
fi

# Install Cert-Manager: used for managing TLS certificates for external services and pgbackrest; also required for MetalLB and Contour
echo "Installing Cert-Manager..."
helm install cert-manager ./cert-manager --namespace cert-manager --create-namespace --set crds.enabled=true
kubectl wait --for=condition=Available deployment --all -n cert-manager --timeout=120s
if [ $? -ne 0 ]; then
    echo "Error: Cert-Manager installation failed."
    exit 1
fi
kubectl apply -f "$SCRIPT_DIR/system/certificate-selfsigned.yaml"
if [ $? -ne 0 ]; then
    echo "Error: Failed to create Selfsigned ClusterIssuer."
    exit 1
fi

# Install MetalLB
echo "Checking if MetalLB namespace exists..."
if ! kubectl get namespace metallb-system > /dev/null 2>&1; then
  echo "Creating MetalLB namespace..."
  kubectl create namespace metallb-system
fi
echo "Labeling MetalLB namespace for privileged security context..."
kubectl label namespace metallb-system \
  pod-security.kubernetes.io/enforce=privileged \
  pod-security.kubernetes.io/audit=privileged \
  pod-security.kubernetes.io/warn=privileged || {
    echo "Failed to label MetalLB namespace. Exiting." >&2
    exit 1
  }
echo "Installing MetalLB with Helm..."
helm install metallb ./metallb -n metallb-system || {
  echo "Failed to install MetalLB using Helm. Exiting." >&2
  exit 1
}
echo "Waiting for MetalLB pods to be ready..."
kubectl rollout status deployment/metallb-controller -n metallb-system || {
  echo "MetalLB controller rollout failed. Exiting." >&2
  exit 1
}
kubectl wait --for=condition=Available deployment --all -n metallb-system --timeout=300s || {
  echo "MetalLB pods did not become available within the timeout period. Exiting." >&2
  exit 1
}
echo "Applying MetalLB configuration..."
if ! kubectl apply -f "$SCRIPT_DIR/system/metallb-config.yaml"; then
  echo "Failed to apply MetalLB configuration. Exiting." >&2
  exit 1
fi
echo "MetalLB installation and configuration complete."

# Install Longhorn
echo "Installing Longhorn..."
helm install longhorn longhorn/longhorn --namespace longhorn-system --create-namespace --set persistence.defaultClass=true
echo "Waiting for Longhorn pods to be ready..."
kubectl rollout status deployment/longhorn-manager -n longhorn-system

# Install Contour Ingress controller (used for routing external traffic to services)
if [ "$K8S_CONTROLLER" == 1 ]; then
  echo "Installing Contour Ingress controller..."
  helm install contour ./contour -n projectcontour --create-namespace --set ingressController.service.type=LoadBalancer
  if [ $? -ne 0 ]; then
      echo "Error occurred during Contour installation."
      exit 1
  fi
  kubectl rollout status deployment/contour-contour -n projectcontour
  echo "Waiting for Envoy DaemonSet pods to be ready..."
  kubectl wait --for=condition=Ready pod -l app.kubernetes.io/component=envoy -n projectcontour --timeout=300s
  kubectl get all -n projectcontour  # Check after rollout
fi

# Create the RoleBinding for kube-scheduler
echo "Creating RoleBinding for kube-scheduler..."
kubectl create rolebinding -n kube-system extension-apiserver-authentication-reader --role=extension-apiserver-authentication-reader --serviceaccount=kube-system:kube-scheduler
if [ $? -ne 0 ]; then
    echo "Error occurred while creating the RoleBinding."
    exit 1
fi

# Fetch remote secrets and create Kubernetes secrets
source "$SCRIPT_DIR/load-secrets.sh"

# Create required directories for persistent storage; clone WHG database
source "$SCRIPT_DIR/create-persistent-volumes.sh"

# Exit if this is a worker node
if [ "$K8S_CONTROLLER" != 1 ]; then
  echo "Worker node setup complete."
  exit 0
fi

#### Deploy Control Plane Components ####

# Install Kubernetes Dashboard together with an Ingress Resource, Authentication, and a dedicated subdomain
echo "Deploying Kubernetes Dashboard via LoadBalancer..."

# Install Kubernetes Dashboard
echo "Installing Kubernetes Dashboard..."
#  kubectl create namespace kubernetes-dashboard  # Ensure the kubernetes-dashboard namespace exists
kubectl apply -f https://raw.githubusercontent.com/kubernetes/dashboard/v2.7.0/aio/deploy/recommended.yaml
kubectl rollout status deployment/kubernetes-dashboard -n kubernetes-dashboard
kubectl apply -f "$SCRIPT_DIR/system/dashboard-service.yaml" # Apply Dashboard Service configuration

# Wait for LoadBalancer IP assignment
echo "Waiting for LoadBalancer IP for Kubernetes Dashboard..."
while true; do
  LB_IP=$(kubectl get svc kubernetes-dashboard-lb -n kubernetes-dashboard -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
  if [[ -n "$LB_IP" ]]; then
    echo "Kubernetes Dashboard is accessible at https://$LB_IP"
    break
  fi
  echo "Still waiting for LoadBalancer IP..."
  sleep 5
done

# Create ServiceAccount and ClusterRoleBinding in the kubernetes-dashboard namespace
echo "Creating ServiceAccount for Dashboard access..."
kubectl create serviceaccount dashboard-admin -n kubernetes-dashboard
kubectl create clusterrolebinding dashboard-admin-binding --clusterrole=cluster-admin --serviceaccount=kubernetes-dashboard:dashboard-admin

# Get the Dashboard token
TOKEN=$(kubectl -n kubernetes-dashboard create token dashboard-admin --duration=876600h) # Create a token with 100-year validity

# Add the credentials to the user kubeconfig files
USER_HOME="/home/$SUDO_USER"
USER_KUBE_CONFIG="$USER_HOME/.kube/config"
kubectl --kubeconfig="$USER_KUBE_CONFIG" config set-credentials "dashboard-admin" --token="$TOKEN"
kubectl --kubeconfig="$USER_KUBE_CONFIG" config set-context "dashboard-context" --cluster=$(kubectl --kubeconfig="$USER_KUBE_CONFIG" config view -o=jsonpath='{.current-context}') --user="dashboard-admin"
kubectl --kubeconfig="$USER_KUBE_CONFIG" config use-context "dashboard-context"

# Echo the URL and token
echo "Kubernetes Dashboard is available at: https://$LB_IP"
echo "Log in using either the config file at $USER_KUBE_CONFIG or the following token:"
echo "$TOKEN"

# Deploy Prometheus and Grafana (based on `kube-prometheus`)
echo "Waiting for prometheus-grafana CustomResourceDefinitions to be applied and established..."
kubectl apply --server-side -f "$SCRIPT_DIR/prometheus-grafana/charts/prometheus/crds"
if [ $? -ne 0 ]; then
    echo "Error: Failed to apply prometheus-grafana CustomResourceDefinitions."
    exit 1
fi
kubectl wait --for=condition=Established --all CustomResourceDefinition --timeout=300s
if [ $? -ne 0 ]; then
    echo "Error: CRDs were not established within the timeout period."
    exit 1
else
    echo "CRDs established successfully."
fi
helm dependency build ./prometheus-grafana
helm install prometheus-grafana ./prometheus-grafana

##  Deploy Plausible Analytics
helm dependency build ./plausible-analytics
helm install plausible-analytics ./plausible-analytics

##  Deploy Glitchtip
kubectl get secret whg-secret -o json \
  | jq 'del(.metadata.ownerReferences) | .metadata.namespace = "monitoring" | del(.metadata.resourceVersion, .metadata.uid, .metadata.creationTimestamp)' \
  | kubectl apply -f -
helm install glitchtip ./glitchtip

# Apply global label critical=true to all resources
echo "Labeling all resources as critical..."
RESOURCES=("pods" "deployments" "services" "configmaps" "secrets" "statefulsets" "daemonsets" "replicasets" "jobs" "cronjobs" "persistentvolumes" "persistentvolumeclaims")
for RESOURCE in "${RESOURCES[@]}"; do
    kubectl label "$RESOURCE" --all --all-namespaces critical=true
done

# Deploy services (only on control-plane nodes)
bash "$SCRIPT_DIR/deploy-services.sh"

echo "Completed server configuration and deployment of Kubernetes components."

###############################
# ORIGINAL deploy-services.sh #
###############################

# Set logging
export LOG_FILE="/var/log/kubernetes-setup.log"
exec > >(tee -i $LOG_FILE) 2>&1

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run this script as root or with sudo."
    exit 1
fi

# Identify the absolute path of this script's directory; load helper functions
export SCRIPT_DIR="$(realpath "$(dirname "${BASH_SOURCE[0]}")")"
source "$SCRIPT_DIR/functions.sh"

# Identify the Kubernetes environment, set variables
identify_environment

# Remove any previous service installations
source "$SCRIPT_DIR/kill-services.sh"

# Deploy Tile services
echo "Deploying Tile services..."
if [ "$K8S_ID" == "local" ]; then
  SERVICE_TYPE="NodePort"
else
  SERVICE_TYPE="LoadBalancer"
fi
helm install tileserver ./tileserver --set service.type=$SERVICE_TYPE


# Deploy WHG services
echo "Deploying WHG services..."
helm install whg ./whg

# Deploy Vespa manifests
echo "Deploying Vespa components..."
helm install vespa ./vespa
# kubectl exec -it vespa-admin-0 --n vespa -- vespa deploy --config-dir /opt/vespa/etc/vespa ????

# Deploy Linguistics service
#echo "Deploying Linguistics service..."
#helm install linguistics ./linguistics

if [ "$K8S_CONTROLLER" == 1 ]; then

  #  Deploy Wordpress (for blog.whgazetteer.org)
#  echo "Deploying Wordpress..."
#  kubectl apply -f "$SCRIPT_DIR/wordpress/wordpress-mariadb-pv-pvc.yaml"
#  helm install wordpress ./wordpress
#  kubectl port-forward svc/wordpress 8081:80 &
  echo "Wordpress requires manual configuration."

fi

# Print summary of all resources
kubectl get all

# Print instructions for describing or starting a shell in a pod
echo "-------------------------------------------------------------"
echo "To describe a pod, run:"
echo "kubectl describe pod <pod-name>"
echo "-------------------------------------------------------------"
echo "To start a shell in a pod, run:"
echo "kubectl exec -it <pod-name> -- /bin/bash"
echo "-------------------------------------------------------------"

# Print instructions for deployment of worker nodes
if [ "$ROLE" == "master" ]; then
  # Print the join command for workers
  JOIN_COMMAND=$(kubeadm token create --print-join-command)
  echo "-------------------------------------------------------------"
  echo "To join worker nodes to the cluster, run this deployment script with the following parameters:"
  echo "sudo ./server-configuration/deploy.sh ROLE=worker JOIN_COMMAND=\"$JOIN_COMMAND\""
  echo "-------------------------------------------------------------"
fi

