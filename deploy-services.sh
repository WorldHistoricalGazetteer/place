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
if [[ "$K8S_ROLE" == "all" || "$K8S_ROLE" == "general" ]]; then

  # Deploy TileServer-GL
  echo "Deploying Tile services..."
  kubectl apply -f "$SCRIPT_DIR/tileserver/tileserver-gl-pv-pvc.yaml"
  yq e '.spec.template.spec.volumes += [{"name": "assets", "hostPath": {"path": "'$SCRIPT_DIR'/tileserver/assets/", "type": "Directory"}}]' "$SCRIPT_DIR/tileserver/tileserver-gl-deployment.yaml" | kubectl apply -f -
  if [ "$K8S_ENVIRONMENT" == "development" ]; then
    kubectl apply -f "$SCRIPT_DIR/tileserver/tileserver-gl-service-local.yaml" # Serve on http://localhost:30080
  else
    kubectl apply -f "$SCRIPT_DIR/tileserver/tileserver-gl-service.yaml"
    yq e "$YQ_TLS" "$SCRIPT_DIR/tileserver/tileserver-gl-ingress.yaml" | kubectl apply -f - # Remove cert-manager and tls section for worker nodes
  fi

fi

# Deploy WHG services
echo "Deploying WHG services..."
kubectl create namespace whg
kubectl get secret whg-secret -o json \
  | jq 'del(.metadata.ownerReferences) | .metadata.namespace = "whg"' \
  | kubectl apply -f -
helm install whg ./whg

# Deploy Vespa manifests
echo "Deploying Vespa components..."
helm install vespa ./vespa

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
