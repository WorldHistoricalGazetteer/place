#!/bin/bash

# Define script directory
SCRIPT_DIR=$(dirname "$0")

echo "Deploying Tile services..."

# Deploy TileServer-GL
# TODO: Create a Persistent Volume (PV) with hostPath for use by the TileServer-GL PVC - and consider Cloud Storage options
kubectl apply -f "$SCRIPT_DIR/tileserver/tileserver-gl-pvc.yaml"
kubectl apply -f "$SCRIPT_DIR/tileserver/tileserver-gl-deployment.yaml"
kubectl apply -f "$SCRIPT_DIR/tileserver/tileserver-gl-service.yaml"
yq e "$YQ_TLS" "$SCRIPT_DIR/tileserver/tileserver-gl-ingress.yaml" | kubectl apply -f -

# Deploy Node server for Tippecanoe
# TODO: Build and push the docker image to DockerHub
kubectl apply -f "$SCRIPT_DIR/tileserver/tippecanoe-deployment.yaml"
kubectl apply -f "$SCRIPT_DIR/tileserver/tippecanoe-service.yaml"