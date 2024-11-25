#!/bin/bash

# Get role (master, worker, or local)
ROLE=$1
if [ -z "$ROLE" ]; then
    echo "Error: Role (master, worker, or local) must be specified."
    exit 1
fi

if [ "$ROLE" == "master" ]; then
  YQ_TLS='.'  # No changes to the file (pass it as is)
else
  YQ_TLS='del(.metadata.annotations["cert-manager.io/cluster-issuer"], .spec.tls)'  # Remove cert-manager and tls section
fi

# Define script directory
SCRIPT_DIR=$(dirname "$0")

# Remove any previous Kubernetes installation
# sudo bash "$SCRIPT_DIR/remove-kubernetes.sh" # This fails to release the necessary ports: server reboot is required

# Update and install dependencies
echo "Updating package list..."
sudo apt-get update
if [ $? -ne 0 ]; then
    echo "Error occurred during package list update."
    exit 1
fi

sudo apt-get install -qy apt-transport-https ca-certificates curl software-properties-common jq containerd
if [ $? -ne 0 ]; then
    echo "Error occurred during the installation of dependencies."
    exit 1
fi

sudo wget -O /usr/local/bin/yq https://github.com/mikefarah/yq/releases/download/v4.13.0/yq_linux_amd64
if [ $? -ne 0 ]; then
    echo "Error occurred while downloading yq."
    exit 1
fi

sudo chmod +x /usr/local/bin/yq

# Load configuration from YAML files
KUBE_VERSION=$(yq eval '.kubernetes.version' "$SCRIPT_DIR/system/kubernetes-config.yaml")
KUBE_REPO_URL=$(yq eval '.kubernetes.repo_url' "$SCRIPT_DIR/system/kubernetes-config.yaml")
POD_NETWORK_CIDR=$(yq eval '.kubernetes.pod_network_cidr' "$SCRIPT_DIR/system/kubernetes-config.yaml")
HELM_VERSION=$(yq eval '.helm.version' "$SCRIPT_DIR/system/helm-config.yaml")
HELM_REPO_URL=$(yq eval '.helm.repo_url' "$SCRIPT_DIR/system/helm-config.yaml")
VESPA_VERSION=$(yq eval '.vespa.version' "$SCRIPT_DIR/system/vespa-config.yaml")
VESPA_DOWNLOAD_URL=$(yq eval '.vespa.download_url' "$SCRIPT_DIR/system/vespa-config.yaml")

# Enable and start containerd
echo "Enabling and starting containerd..."

# Ensure the containerd config file exists
if [ ! -f /etc/containerd/config.toml ]; then
    echo "Containerd config file not found! Exiting."
    exit 1
fi

# Modify the containerd configuration to ensure the 'cri' plugin is enabled
echo "Enabling the CRI plugin in containerd configuration..."
sudo sed -i '/disabled_plugins = \["cri"\]/d' /etc/containerd/config.toml

# Start containerd to apply changes
echo "Starting containerd..."
sudo systemctl start containerd

# Check containerd version to ensure it's running correctly
containerd --version
if [ $? -ne 0 ]; then
    echo "Error occurred while starting containerd."
    exit 1
fi

echo "Containerd is running with the CRI plugin enabled."

# Add Kubernetes GPG key
echo "Adding Kubernetes GPG key..."
if sudo curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.30/deb/Release.key | sudo gpg --yes --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg; then
    echo "Kubernetes GPG key added successfully."
else
    echo "Failed to add Kubernetes GPG key."
    exit 1
fi

# Add Kubernetes repository with the signed-by option
echo "Adding Kubernetes repository..."
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.30/deb/ /" | sudo tee /etc/apt/sources.list.d/kubernetes.list > /dev/null

# Update the package index
echo "Updating package list..."
sudo apt-get update -q

# Install Kubernetes components
echo "Installing Kubernetes version $KUBE_VERSION..."
if sudo apt-get install -qy kubelet="$KUBE_VERSION" kubeadm="$KUBE_VERSION" kubectl="$KUBE_VERSION"; then
    echo "Kubernetes $KUBE_VERSION installed successfully."
else
    echo "Specified Kubernetes version $KUBE_VERSION not found. Installing the latest version instead."
    # Install the latest Kubernetes version
    if sudo apt-get install -qy kubelet kubeadm kubectl conntrack cri-tools kubernetes-cni; then
        echo "Latest Kubernetes version installed successfully."
    else
        echo "Failed to install Kubernetes. Please check the repository configuration."
        exit 1
    fi
fi

# Check if kubectl was installed correctly
kubectl version --client
if [ $? -ne 0 ]; then
    echo "Error occurred while checking Kubernetes version."
    exit 1
fi

# Disable swap (required for Kubernetes)
echo "Disabling swap..."
sudo swapoff -a
sudo sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab

# Enable and start kubelet
echo "Enabling and starting kubelet..."
sudo systemctl enable kubelet
sudo systemctl start kubelet
if [ $? -ne 0 ]; then
    echo "Error occurred while starting kubelet."
    exit 1
fi

if [[ "$ROLE" == "master" || "$ROLE" == "local" ]]; then
  # Initialize Kubernetes cluster
  echo "Initializing Kubernetes cluster with pod network CIDR $POD_NETWORK_CIDR..."
  sudo kubeadm init --pod-network-cidr=$POD_NETWORK_CIDR
  if [ $? -ne 0 ]; then
      echo "Error occurred during Kubernetes cluster initialization."
      exit 1
  fi
elif [ "$ROLE" == "worker" ]; then
  # Ensure JOIN_COMMAND is passed as an argument
  if [ -z "$JOIN_COMMAND" ]; then
      echo "Error: JOIN_COMMAND must be provided to join the worker node."
      exit 1
  fi

  # Join the worker node to the Kubernetes cluster
  echo "Joining the worker node to the Kubernetes cluster using the provided join command..."
  sudo $JOIN_COMMAND
  if [ $? -ne 0 ]; then
      echo "Error occurred while joining the worker node to the Kubernetes cluster."
      exit 1
  fi
fi

# Configure kubectl
echo "Configuring kubectl..."
mkdir -p $HOME/.kube
sudo cp /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config
kubectl get nodes
kubectl get pods -n kube-system
if [ $? -ne 0 ]; then
    echo "Error occurred while configuring kubectl."
    exit 1
fi

# Install Helm
echo "Installing Helm version $HELM_VERSION..."
curl -fsSL "$HELM_REPO_URL/helm-v$HELM_VERSION-linux-amd64.tar.gz" -o helm.tar.gz
if [ $? -ne 0 ]; then
    echo "Error occurred while downloading Helm."
    exit 1
fi

tar -zxvf helm.tar.gz
sudo mv linux-amd64/helm /usr/local/bin/helm
sudo rm -rf linux-amd64 helm.tar.gz
helm version
if [ $? -ne 0 ]; then
    echo "Error occurred while checking Helm version."
    exit 1
fi

# Install Flannel
echo "Installing Flannel for Kubernetes..."
kubectl apply -f "$SCRIPT_DIR/system/flannel-config.yaml"
kubectl get pods -n kube-system -l app=flannel
if [ $? -ne 0 ]; then
    echo "Error occurred during Flannel installation."
    exit 1
fi

if [[ "$ROLE" == "master" || "$ROLE" == "local" ]]; then
  # Install Contour
  echo "Installing Contour Ingress controller..."
  kubectl apply -f "$SCRIPT_DIR/system/contour-config.yaml"
  kubectl get pods -n projectcontour
  if [ $? -ne 0 ]; then
      echo "Error occurred during Contour installation."
      exit 1
  fi
fi

if [ "$ROLE" == "master" ]; then
  # Install Cert-Manager
  echo "Installing Cert-Manager..."
  kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.12.0/cert-manager.yaml
  kubectl wait --for=condition=Available deployment --all -n cert-manager --timeout=120s
  if [ $? -ne 0 ]; then
      echo "Error: Cert-Manager installation failed."
      exit 1
  fi
  kubectl apply -f "$SCRIPT_DIR/system/certificate-config.yaml"
  if [ $? -ne 0 ]; then
      echo "Error: Failed to create ClusterIssuer."
      exit 1
  fi
fi

# Install Vespa CLI
echo "Installing Vespa CLI version $VESPA_VERSION..."
curl -LO $VESPA_DOWNLOAD_URL
if [ $? -ne 0 ]; then
    echo "Error occurred while downloading Vespa CLI."
    exit 1
fi

tar -xvf vespa-cli_${VESPA_VERSION}_linux_amd64.tar.gz
sudo mv vespa-cli_${VESPA_VERSION}_linux_amd64/bin/vespa /usr/local/bin/
sudo rm -rf vespa-cli_${VESPA_VERSION}_linux_amd64 vespa-cli_${VESPA_VERSION}_linux_amd64.tar.gz
vespa version || { echo "Vespa CLI installation failed"; exit 1; }

# TODO: Install Kubernetes Dashboard together with an Ingress Resource, Authentication, and a dedicated subdomain

echo "Completed server configuration and deployment of Kubernetes components."

sudo bash "$SCRIPT_DIR/deploy-services.sh"