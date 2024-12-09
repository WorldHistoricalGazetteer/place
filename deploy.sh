#!/bin/bash

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
export SCRIPT_DIR="$(realpath "$(dirname "${BASH_SOURCE[0]}")")"
source "$SCRIPT_DIR/functions.sh"

# Identify the Kubernetes environment, set variables
identify_environment
export KUBECONFIG=/etc/kubernetes/admin.conf

# Remove any previous Kubernetes installation
remove_kubernetes

#### Install required packages and configure the system ####

# Define required packages
REQUIRED_PKGS=("apt-transport-https" "ca-certificates" "curl" "software-properties-common" "jq" "docker-ce" "docker-ce-cli" "containerd.io=1.7.23-1" "kubelet" "kubeadm" "kubectl" "conntrack" "cri-tools" "kubernetes-cni")
PAUSE_IMAGE="registry.k8s.io/pause:3.10" # Default pause image, to be used by both kubelet and containerd

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

# Install required packages
echo "Checking required packages..."
for PKG in "${REQUIRED_PKGS[@]}"; do
    # Check if the package is installed using dpkg-query
    if ! dpkg-query -W -f='${Status}' $PKG 2>/dev/null | grep -q "install ok installed"; then
        echo "Installing $PKG..."
        if ! apt-get install -qy $PKG --allow-downgrades; then
            echo "Error: Failed to install $PKG. Exiting."
            exit 1
        fi
    else
        echo "$PKG is already installed."
    fi
done

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
echo "Overriding kubelet configuration..."
OVERRIDE_FILE="/etc/systemd/system/kubelet.service.d/override.conf"
mkdir -p $(dirname $OVERRIDE_FILE)
tee $OVERRIDE_FILE > /dev/null <<EOF
[Service]
Environment="KUBELET_EXTRA_ARGS=--cgroup-driver=systemd --pod-infra-container-image=$PAUSE_IMAGE"
EOF
systemctl daemon-reload

if [ "$K8S_CONTROLLER" == 1 ]; then

  # Initialize Kubernetes cluster
  echo "Initializing Kubernetes cluster with pod network CIDR 10.244.0.0/16..."
  kubeadm config images pull
  kubeadm init -v=9 --pod-network-cidr=10.244.0.0/16
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

# Label nodes based on K8S_CONTROLLER, K8S_ROLE, and K8S_ENVIRONMENT; always allow pods on a control plane node
kubectl label nodes --all controller=$K8S_CONTROLLER role=$K8S_ROLE environment=$K8S_ENVIRONMENT
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

# Install Kubernetes Dashboard together with an Ingress Resource, Authentication, and a dedicated subdomain
if [ "$K8S_CONTROLLER" == 1 ]; then
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

  # Deploy services (only on control-plane nodes)
  bash "$SCRIPT_DIR/deploy-services.sh"
fi

echo "Completed server configuration and deployment of Kubernetes components."