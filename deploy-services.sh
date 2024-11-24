# Define script directory

# Get role (master, worker, or local)
ROLE=$1
if [ -z "$ROLE" ]; then
    echo "Error: Role (master, worker, or local) must be specified."
    exit 1
fi

SCRIPT_DIR=$(dirname "$0")

# Remove any previous service installations, keeping persistent volume claims
for dir in "$SCRIPT_DIR/django" "$SCRIPT_DIR/tileserver" "$SCRIPT_DIR/vespa"; do
  find "$dir" -type f -name "*.yaml" ! -name "*-pvc.yaml" -exec kubectl delete -f {} \; || true
done

# Deploy Django and Tile services
if [[ "$ROLE" == "master" || "$ROLE" == "local" ]]; then
  bash "$SCRIPT_DIR/deploy-service-django.sh"
  bash "$SCRIPT_DIR/deploy-service-tileserver.sh"
fi

# Deploy Vespa manifests
echo "Deploying Vespa components..."
kubectl apply -f "$SCRIPT_DIR/vespa/content-node-deployment.yaml"
kubectl apply -f "$SCRIPT_DIR/vespa/search-node-deployment.yaml"
if [[ "$ROLE" == "master" || "$ROLE" == "local" ]]; then
  kubectl apply -f "$SCRIPT_DIR/vespa/config-server-deployment.yaml"
  yq e "$YQ_TLS" "$SCRIPT_DIR/vespa/vespa-ingress.yaml" | kubectl apply -f -
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
