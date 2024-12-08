#!/bin/bash

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

# Define script directory
SCRIPT_DIR=$(dirname "$0")
SCRIPT_DIR=$(realpath "$SCRIPT_DIR")

echo "Deploying Tile services..."

# Deploy TileServer-GL
kubectl apply -f "$SCRIPT_DIR/tileserver/tileserver-gl-pv-pvc.yaml"
yq e '.spec.template.spec.volumes += [{"name": "assets", "hostPath": {"path": "'$SCRIPT_DIR'/tileserver/assets/", "type": "Directory"}}]' "$SCRIPT_DIR/tileserver/tileserver-gl-deployment.yaml" | kubectl apply -f -
if [ "$ROLE" == "local" ]; then
  kubectl apply -f "$SCRIPT_DIR/tileserver/tileserver-gl-service-local.yaml" # Serve on http://localhost:30080
else
  kubectl apply -f "$SCRIPT_DIR/tileserver/tileserver-gl-service.yaml"
  yq e "$YQ_TLS" "$SCRIPT_DIR/tileserver/tileserver-gl-ingress.yaml" | kubectl apply -f - # Remove cert-manager and tls section for worker nodes
fi

# Deploy Node server for Tippecanoe
## TODO: Build and push the docker image to DockerHub
#kubectl apply -f "$SCRIPT_DIR/tippecanoe/tippecanoe-deployment.yaml"
#kubectl apply -f "$SCRIPT_DIR/tippecanoe/tippecanoe-service.yaml"