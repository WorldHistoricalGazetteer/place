#!/bin/bash

#### Prepare the environment ####

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
REQUIRED_PKGS=("apt-transport-https" "ca-certificates" "curl" "software-properties-common" "jq" "docker-ce" "docker-ce-cli" "containerd.io=1.7.23-1" "kubelet" "kubeadm" "kubectl" "conntrack" "cri-tools" "kubernetes-cni")
PAUSE_IMAGE="registry.k8s.io/pause:3.10" # Default pause image, to be used by both kubelet and containerd
export KUBECONFIG=/etc/kubernetes/admin.conf

# Validate input
if [[ "$ROLE" != "master" && "$ROLE" != "worker" && "$ROLE" != "local" ]]; then
    echo "Invalid ROLE specified. Use 'master', 'worker', or 'local'."
    exit 1
fi

# Remove any previous Kubernetes installation
bash "$SCRIPT_DIR/remove-kubernetes.sh"

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
        if ! apt-get install -qy $PKG; then
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
if [[ "$ROLE" == "master" || "$ROLE" == "local" ]]; then
  # Control Plane Node
  iptables -A INPUT -p tcp --dport 6443 -j ACCEPT # Allow Kubernetes API server
  iptables -A INPUT -p tcp --dport 2379:2380 -j ACCEPT # Allow etcd server client API
  iptables -A INPUT -p tcp --dport 10251 -j ACCEPT # Allow kube-scheduler
  iptables -A INPUT -p tcp --dport 10252 -j ACCEPT # Allow kube-controller-manager
elif [ "$ROLE" == "worker" ]; then
  # Worker Node
  iptables -A INPUT -p tcp --dport 30000:32767 -j ACCEPT # Allow NodePort Services
fi

#### Helper functions ####

# Wait for the Kubernetes control-plane to be ready
wait_for_k8s() {
    echo "Waiting for Kubernetes control-plane to become ready..."
#    until kubectl version --short &>/dev/null; do sleep 5; done
    until kubectl get nodes | grep -q "Ready"; do sleep 5; done
    echo "Control-plane is ready!"
}

# Function to check if the kubelet is running
check_kubelet_status() {
    echo "Checking kubelet status..."
    systemctl is-active --quiet kubelet
    local status=$?

    if [ $status -ne 0 ]; then
        echo "Error: Kubelet service is not running."
    else
        echo "Kubelet service is running."
    fi
    return $status
}

# Wait for the kubelet to be active
wait_for_kubelet() {
    echo "Waiting for kubelet to be active..."
    while true; do
        if check_kubelet_status; then
            echo "Kubelet is active."
            break
        else
            echo "Kubelet is not active, retrying..."
            sleep 5
        fi
    done
}

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

if [[ "$ROLE" == "master" || "$ROLE" == "local" ]]; then

  # Initialize Kubernetes cluster
  echo "Initializing Kubernetes cluster with pod network CIDR 10.244.0.0/16..."
  kubeadm config images pull
  kubeadm init -v=9 --pod-network-cidr=10.244.0.0/16
  if [ $? -ne 0 ]; then
      echo "Error occurred during Kubernetes cluster initialization."
      exit 1
  fi
  wait_for_k8s # Wait for the Kubernetes control-plane to be ready

fi

# Install Flannel (CNI = Container Network Interface) for Kubernetes
echo "Installing Flannel for Kubernetes..."
helm install flannel ./flannel -n kube-system
echo "Waiting for Flannel network pods to be ready..."
kubectl rollout status daemonset/kube-flannel-ds -n kube-system

# Allow local node to run pods
if [ "$ROLE" == "local" ]; then
  if kubectl describe node $(hostname) | grep -q "Taints:.*node-role.kubernetes.io/master"; then
    kubectl taint nodes --all node-role.kubernetes.io/master-
  else
    echo "No taint found for node-role.kubernetes.io/master, skipping removal."
  fi
fi

# Join worker node if applicable
if [ "$ROLE" == "worker" ]; then
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

# Verify kubectl can access the cluster
kubectl get nodes
kubectl get pods -n kube-system
if [ $? -ne 0 ]; then
    echo "Error occurred while configuring kubectl."
    exit 1
fi

# Create the RoleBinding for kube-scheduler
#echo "Creating RoleBinding for kube-scheduler..."
#kubectl create rolebinding -n kube-system extension-apiserver-authentication-reader --role=extension-apiserver-authentication-reader --serviceaccount=kube-system:kube-scheduler
#if [ $? -ne 0 ]; then
#    echo "Error occurred while creating the RoleBinding."
#    exit 1
#fi

#if [[ "$ROLE" == "master" || "$ROLE" == "local" ]]; then
#  # Install Cert-Manager: used for managing TLS certificates for external services
#  echo "Installing Cert-Manager..."
#  kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.12.0/cert-manager.yaml
#  kubectl wait --for=condition=Available deployment --all -n cert-manager --timeout=120s
#  if [ $? -ne 0 ]; then
#      echo "Error: Cert-Manager installation failed."
#      exit 1
#  fi
#  kubectl apply -f "$SCRIPT_DIR/system/certificate-config.yaml"
#  if [ $? -ne 0 ]; then
#      echo "Error: Failed to create ClusterIssuer."
#      exit 1
#  fi
#fi

#if [[ "$ROLE" == "master" || "$ROLE" == "local" ]]; then
#  # Install Contour
#  echo "Installing Contour Ingress controller..."
#  helm install contour bitnami/contour -n projectcontour --create-namespace
#  if [ $? -ne 0 ]; then
#      echo "Error occurred during Contour installation."
#      exit 1
#  fi
#  kubectl get pods -n projectcontour
#fi

## Install Vespa CLI
#echo "Installing Vespa CLI version $VESPA_VERSION..."
#curl -LO $VESPA_DOWNLOAD_URL
#if [ $? -ne 0 ]; then
#    echo "Error occurred while downloading Vespa CLI."
#    exit 1
#fi
#
#tar -xvf vespa-cli_${VESPA_VERSION}_linux_amd64.tar.gz
#mv vespa-cli_${VESPA_VERSION}_linux_amd64/bin/vespa /usr/local/bin/
#rm -rf vespa-cli_${VESPA_VERSION}_linux_amd64 vespa-cli_${VESPA_VERSION}_linux_amd64.tar.gz
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

#bash "$SCRIPT_DIR/deploy-services.sh" "$ROLE"