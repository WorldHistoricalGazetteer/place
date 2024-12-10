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

## Remove any previous service installations
#for dir in "$SCRIPT_DIR/django" "$SCRIPT_DIR/tileserver" "$SCRIPT_DIR/vespa"; do
##  find "$dir" -type f -name "*.yaml" ! -name "*-pvc.yaml" -exec kubectl delete -f {} \; || true # Do not delete PVCs
#  find "$dir" -type f -name "*.yaml" ! -name "*-pv.yaml" -exec kubectl delete -f {} \; || true # Do not delete PVs
##  find "$dir" -type f -name "*.yaml" -exec kubectl delete -f {} \; || true
#done

# Deploy Django and Tile services
if [[ "$K8S_ROLE" == "all" || "$K8S_ROLE" == "general" ]]; then
  bash "$SCRIPT_DIR/deploy-service-django.sh"

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

# Deploy Vespa manifests
#echo "Deploying Vespa components..."
#kubectl apply -f "$SCRIPT_DIR/vespa/content-node-deployment.yaml"
#kubectl apply -f "$SCRIPT_DIR/vespa/search-node-deployment.yaml"
#if [[ "$ROLE" == "master" || "$ROLE" == "local" ]]; then
#  kubectl apply -f "$SCRIPT_DIR/vespa/config-server-deployment.yaml"
#  yq e "$YQ_TLS" "$SCRIPT_DIR/vespa/vespa-ingress.yaml" | kubectl apply -f -
#fi

if [ "$K8S_CONTROLLER" == 1 ]; then

  #  Deploy Wordpress (for blog.whgazetteer.org)
#  echo "Deploying Wordpress..."
#  kubectl apply -f "$SCRIPT_DIR/wordpress/wordpress-mariadb-pv-pvc.yaml"
#  helm install wordpress ./wordpress
#  kubectl port-forward svc/wordpress 8081:80 &
  echo "Wordpress requires manual configuration."

#  NAME                    URL
#  bitnami                 https://charts.bitnami.com/bitnami
#  zekker6                 https://zekker6.github.io/helm-charts/
#  glitchtip               https://gitlab.com/api/v4/projects/16325141/packages/helm/stable
#  grafana                 https://grafana.github.io/helm-charts
#  prometheus-community    https://prometheus-community.github.io/helm-charts

#  echo "Deploying monitoring components..."
#  # TODO: Configure all values.yaml files for monitoring components

#  Deploy Prometheus
  kubectl apply -f "$SCRIPT_DIR/prometheus/prometheus-pv-pvc.yaml"
  helm install prometheus ./prometheus

#  Deploy Grafana
  kubectl apply -f "$SCRIPT_DIR/grafana/grafana-pv-pvc.yaml"
  helm install grafana ./grafana

#  Deploy Plausible
#  See https://zekker6.github.io/helm-charts/docs/charts/plausible-analytics/#configuration
  kubectl apply -f "$SCRIPT_DIR/plausible/plausible-pv-pvc.yaml"
  helm install plausible-analytics ./plausible-analytics

#  Deploy Glitchtip
  kubectl apply -f "$SCRIPT_DIR/glitchtip/glitchtip-pv-pvc.yaml"
  helm install glitchtip ./glitchtip

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
