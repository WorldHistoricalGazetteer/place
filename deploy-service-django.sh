#!/bin/bash

# Define script directory
SCRIPT_DIR=$(dirname "$0")

# Deploy Secrets and ConfigMap
echo "Deploying Secrets..."
kubectl apply -f "$SCRIPT_DIR/secret.yaml"
echo "Deploying ConfigMap..."
kubectl apply -f "$SCRIPT_DIR/configmap.yaml"

# Deploy PostgreSQL components
echo "Deploying PostgreSQL..."
kubectl apply -f "$SCRIPT_DIR/django/postgres-pv.yaml"
kubectl apply -f "$SCRIPT_DIR/django/postgres-pvc.yaml"
kubectl apply -f "$SCRIPT_DIR/django/pgbackrest-pv.yaml"
kubectl apply -f "$SCRIPT_DIR/django/pgbackrest-pvc.yaml"
kubectl apply -f "$SCRIPT_DIR/django/postgres-deployment.yaml"
kubectl apply -f "$SCRIPT_DIR/django/postgres-service.yaml"

## Deploy Redis
#echo "Deploying Redis..."
#kubectl apply -f "$SCRIPT_DIR/django/redis-pvc.yaml"
#kubectl apply -f "$SCRIPT_DIR/django/redis-deployment.yaml"
#kubectl apply -f "$SCRIPT_DIR/django/redis-service.yaml"
#
## Deploy Django app
#echo "Deploying Django app..."
## TODO: Create a Persistent Volume (PV) with hostPath for use by the Django PVC
#kubectl apply -f "$SCRIPT_DIR/django/django-pvc.yaml"
#kubectl apply -f "$SCRIPT_DIR/django/django-deployment.yaml"
#kubectl apply -f "$SCRIPT_DIR/django/django-service.yaml"
#yq e "$YQ_TLS" "$SCRIPT_DIR/django/django-ingress.yaml" | kubectl apply -f -
#
## Deploy Celery components
#echo "Deploying Celery components..."
#kubectl apply -f "$SCRIPT_DIR/django/celery-worker-deployment.yaml"
#kubectl apply -f "$SCRIPT_DIR/django/celery-beat-deployment.yaml"
#kubectl apply -f "$SCRIPT_DIR/django/celery-flower-deployment.yaml"
#
## Deploy Webpack
#echo "Deploying Webpack..."
#kubectl apply -f "$SCRIPT_DIR/django/webpack-config.yaml"
#kubectl apply -f "$SCRIPT_DIR/django/webpack-deployment.yaml"
#kubectl apply -f "$SCRIPT_DIR/django/webpack-service.yaml"