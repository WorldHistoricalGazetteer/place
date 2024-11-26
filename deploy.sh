#!/bin/bash

# Set logging
LOG_FILE="/var/log/kubernetes-setup.log"
exec > >(tee -i $LOG_FILE) 2>&1

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run this script as root or with sudo."
    exit 1
fi

# Set defaults
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROLE=${ROLE:-"local"}
REQUIRED_PKGS=("apt-transport-https" "ca-certificates" "curl" "software-properties-common" "jq" "containerd" "kubelet" "kubeadm" "kubectl" "conntrack" "cri-tools" "kubernetes-cni")

# Validate input
if [[ "$ROLE" != "master" && "$ROLE" != "worker" && "$ROLE" != "local" ]]; then
    echo "Invalid ROLE specified. Use 'master', 'worker', or 'local'."
    exit 1
fi

# Remove any previous Kubernetes installation
sudo bash "$SCRIPT_DIR/remove-kubernetes.sh"

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

# Update packages
echo "Updating system package indices..."
if ! sudo apt-get update -qy; then
    echo "Error: Failed to update package list. Exiting."
    exit 1
fi

# Install required packages
echo "Checking required packages..."
for PKG in "${REQUIRED_PKGS[@]}"; do
    # Check if the package is installed using dpkg-query
    if ! dpkg-query -W -f='${Status}' $PKG 2>/dev/null | grep -q "install ok installed"; then
        echo "Installing $PKG..."
        if ! sudo apt-get install -qy $PKG; then
            echo "Error: Failed to install $PKG. Exiting."
            exit 1
        fi
    else
        echo "$PKG is already installed."
    fi
done

# Install containerd
echo "Setting up containerd..."
if ! dpkg -l | grep -q containerd; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
    sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
    sudo apt-get update -qy
    sudo apt-get install -qy containerd.io
fi

# Configure containerd
if [ ! -f /etc/containerd/config.toml ]; then
    echo "Creating default containerd configuration..."
    sudo mkdir -p /etc/containerd
    sudo containerd config default > /etc/containerd/config.toml
    # Modify the containerd configuration to ensure the 'cri' plugin is enabled
    echo "Enabling the CRI plugin in containerd configuration..."
    sudo sed -i '/disabled_plugins = \["cri"\]/d' /etc/containerd/config.toml
fi
if ! sudo systemctl restart containerd; then
    echo "Error: Failed to restart containerd. Exiting."
    exit 1
else
    echo "Containerd is running with the CRI plugin enabled."
fi

sudo wget -O /usr/local/bin/yq https://github.com/mikefarah/yq/releases/download/v4.13.0/yq_linux_amd64
if [ $? -ne 0 ]; then
    echo "Error occurred while downloading yq."
    exit 1
fi
sudo chmod +x /usr/local/bin/yq

if [ "$ROLE" == "master" ]; then
  YQ_TLS='.'  # No changes to the file (pass it as is)
  YQ_TOLERATIONS='.'  # No changes to the file (pass it as is)
elif [ "$ROLE" == "worker" ]; then
  YQ_TLS='del(.metadata.annotations["cert-manager.io/cluster-issuer"], .spec.tls)'  # Remove cert-manager and tls section
  YQ_TOLERATIONS='.'  # No changes to the file (pass it as is)
else # local
  YQ_TLS='del(.metadata.annotations["cert-manager.io/cluster-issuer"], .spec.tls)'  # Remove cert-manager and tls section
  YQ_TOLERATIONS='.spec.template.spec.tolerations += [{"key": "node-role.kubernetes.io/control-plane", "operator": "Exists", "effect": "NoSchedule"}]' # Add tolerations for local node
fi

# Load configuration from YAML files
HELM_VERSION=$(yq eval '.helm.version' "$SCRIPT_DIR/system/helm-config.yaml")
HELM_REPO_URL=$(yq eval '.helm.repo_url' "$SCRIPT_DIR/system/helm-config.yaml")
POD_NETWORK_CIDR=$(yq eval '.kubernetes.pod_network_cidr' "$SCRIPT_DIR/system/kubernetes-config.yaml")
SERVICE_CIDR=$(yq eval '.kubernetes.service_cidr' "$SCRIPT_DIR/system/kubernetes-config.yaml")
#VESPA_VERSION=$(yq eval '.vespa.version' "$SCRIPT_DIR/system/vespa-config.yaml")
#VESPA_DOWNLOAD_URL=$(yq eval '.vespa.download_url' "$SCRIPT_DIR/system/vespa-config.yaml")

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

# Disable swap
echo "Disabling swap..."
sudo swapoff -a
cp /etc/fstab /etc/fstab.bak
sudo sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab
echo "Swap disabled successfully."

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
  echo "Initializing Kubernetes cluster with pod network CIDR $POD_NETWORK_CIDR and service CIDR $SERVICE_CIDR..."
  sudo kubeadm config images pull
  sudo kubeadm init --pod-network-cidr=$POD_NETWORK_CIDR --service-cidr=$SERVICE_CIDR
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

# Check if kubectl was installed correctly
kubectl version --client
if [ $? -ne 0 ]; then
    echo "Error occurred while checking Kubernetes version."
    exit 1
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

# Create the RoleBinding for kube-scheduler
echo "Creating RoleBinding for kube-scheduler..."
kubectl create rolebinding -n kube-system extension-apiserver-authentication-reader --role=extension-apiserver-authentication-reader --serviceaccount=kube-system:kube-scheduler
if [ $? -ne 0 ]; then
    echo "Error occurred while creating the RoleBinding."
    exit 1
fi

# Install Flannel
echo "Installing Flannel for Kubernetes..."
if kubectl apply -f "$SCRIPT_DIR/system/flannel-config.yaml"; then
    echo "Flannel network deployed successfully."
    else
        echo "Error: Flannel network deployment failed. Exiting."
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

## Install Vespa CLI
#echo "Installing Vespa CLI version $VESPA_VERSION..."
#curl -LO $VESPA_DOWNLOAD_URL
#if [ $? -ne 0 ]; then
#    echo "Error occurred while downloading Vespa CLI."
#    exit 1
#fi
#
#tar -xvf vespa-cli_${VESPA_VERSION}_linux_amd64.tar.gz
#sudo mv vespa-cli_${VESPA_VERSION}_linux_amd64/bin/vespa /usr/local/bin/
#sudo rm -rf vespa-cli_${VESPA_VERSION}_linux_amd64 vespa-cli_${VESPA_VERSION}_linux_amd64.tar.gz
#vespa version || { echo "Vespa CLI installation failed"; exit 1; }

# TODO: Install Kubernetes Dashboard together with an Ingress Resource, Authentication, and a dedicated subdomain

#if [ "$ROLE" == "local" ]; then
#  echo "Deploying Kubernetes Dashboard via LoadBalancer..."
#
#  # Install MetalLB
#  echo "Installing MetalLB..."
#  kubectl create namespace metallb-system  # Ensure the metallb-system namespace exists
#  kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/main/config/manifests/metallb-native.yaml  # Install MetalLB
#  kubectl get pods -n metallb-system  # Verify MetalLB components are running
#
#  # Apply the MetalLB config
#  CONFIG_PATH="/home/stephen/PycharmProjects/place/system/metallb-config.yaml"
#  if [ -f "$CONFIG_PATH" ]; then
#    kubectl apply -f "$CONFIG_PATH"  # Apply the MetalLB config
#    kubectl get configmap config -n metallb-system -o yaml  # Verify MetalLB config
#  else
#    echo "Error: $CONFIG_PATH not found. Please ensure the file exists."
#    exit 1
#  fi
#
#  # Install Kubernetes Dashboard
#  kubectl apply -f https://raw.githubusercontent.com/kubernetes/dashboard/v2.7.0/aio/deploy/recommended.yaml
#
#  # Create ServiceAccount and ClusterRoleBinding
#  kubectl create serviceaccount dashboard-admin -n default
#  kubectl create clusterrolebinding dashboard-admin-binding --clusterrole=cluster-admin --serviceaccount=default:dashboard-admin
#
#  # Get the Dashboard token
#  TOKEN=$(kubectl -n default create token dashboard-admin)
#  echo "Dashboard token: $TOKEN"
#
#  # Modify the dashboard service to use LoadBalancer type
#  kubectl patch svc kubernetes-dashboard -n kubernetes-dashboard \
#    -p '{"spec": {"type": "LoadBalancer"}}'
#
#  # Wait for the LoadBalancer to be provisioned
#  echo "Waiting for LoadBalancer external IP to be assigned..."
#  kubectl wait --for=condition=external-ip --timeout=300s svc/kubernetes-dashboard -n kubernetes-dashboard
#
#  # Get the External IP address of the LoadBalancer service
#  EXTERNAL_IP=$(kubectl get svc kubernetes-dashboard -n kubernetes-dashboard -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
#
#  # Echo the URL and token
#  echo "Kubernetes Dashboard is available at: https://$EXTERNAL_IP"
#  echo "Use the following token to log in: $TOKEN"
#fi

echo "Completed server configuration and deployment of Kubernetes components."

#sudo bash "$SCRIPT_DIR/deploy-services.sh" "$ROLE"