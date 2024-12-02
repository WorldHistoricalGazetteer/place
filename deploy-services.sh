#!/bin/bash

# Define script directory

# Get role (master, worker, or local)
ROLE=$1
if [ -z "$ROLE" ]; then
    echo "Error: Role (master, worker, or local) must be specified."
    exit 1
fi

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

SCRIPT_DIR=$(dirname "$0")

## Remove any previous service installations
#for dir in "$SCRIPT_DIR/django" "$SCRIPT_DIR/tileserver" "$SCRIPT_DIR/vespa"; do
##  find "$dir" -type f -name "*.yaml" ! -name "*-pvc.yaml" -exec kubectl delete -f {} \; || true # Do not delete PVCs
#  find "$dir" -type f -name "*.yaml" ! -name "*-pv.yaml" -exec kubectl delete -f {} \; || true # Do not delete PVs
##  find "$dir" -type f -name "*.yaml" -exec kubectl delete -f {} \; || true
#done

# Deploy Django and Tile services
if [[ "$ROLE" == "master" || "$ROLE" == "local" ]]; then
  bash "$SCRIPT_DIR/deploy-service-django.sh" "$ROLE"
#  bash "$SCRIPT_DIR/deploy-service-tileserver.sh"
fi

# Deploy Vespa manifests
#echo "Deploying Vespa components..."
#kubectl apply -f "$SCRIPT_DIR/vespa/content-node-deployment.yaml"
#kubectl apply -f "$SCRIPT_DIR/vespa/search-node-deployment.yaml"
#if [[ "$ROLE" == "master" || "$ROLE" == "local" ]]; then
#  kubectl apply -f "$SCRIPT_DIR/vespa/config-server-deployment.yaml"
#  yq e "$YQ_TLS" "$SCRIPT_DIR/vespa/vespa-ingress.yaml" | kubectl apply -f -
#fi

#if [[ "$ROLE" == "master" || "$ROLE" == "local" ]]; then

#  NAME                    URL
#  bitnami                 https://charts.bitnami.com/bitnami
#  zekker6                 https://zekker6.github.io/helm-charts/
#  glitchtip               https://gitlab.com/api/v4/projects/16325141/packages/helm/stable
#  grafana                 https://grafana.github.io/helm-charts
#  prometheus-community    https://prometheus-community.github.io/helm-charts

#  echo "Deploying monitoring components..."
#  # TODO: Configure all values.yaml files for monitoring components

#  Deploy Wordpress (for blog.whgazetteer.org)
#  helm install wordpress bitnami/wordpress

#  Deploy Prometheus
#  helm install prometheus prometheus-community/prometheus

#  Deploy Grafana
#  helm install grafana grafana/grafana

#  Deploy Plausible
#  See https://zekker6.github.io/helm-charts/docs/charts/plausible-analytics/#configuration
#  helm install plausible-analytics zekker6/plausible-analytics

#  Deploy Glitchtip
#  helm install glitchtip glitchtip/glitchtip

#fi

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
