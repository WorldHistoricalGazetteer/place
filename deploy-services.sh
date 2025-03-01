#!/bin/bash

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
