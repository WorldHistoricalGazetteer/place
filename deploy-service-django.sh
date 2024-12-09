#!/bin/bash

# Get variables from ConfigMap and Secret to construct and append DATABASE_URL
IMAGE_VERSION=$(yq eval '.data["image-version"]' "$SCRIPT_DIR/configmap.yaml")
DB_NAME=$(yq eval '.data["db-name"]' "$SCRIPT_DIR/configmap.yaml")
DB_USER=$(yq eval '.data["db-user"]' "$SCRIPT_DIR/configmap.yaml")
DB_PASSWORD_BASE64=$(yq eval '.data["db-password"]' "$SCRIPT_DIR/whg-private/secret.yaml")
DB_PASSWORD=$(echo "$DB_PASSWORD_BASE64" | base64 --decode)
DATABASE_URL="postgres://$DB_USER:$DB_PASSWORD@postgres:5432/$DB_NAME"
DATABASE_URL_BASE64=$(echo -n "$DATABASE_URL" | base64)

# Deploy Secrets and ConfigMap
echo "Deploying Secrets..."
yq eval ".data.\"db-url\" = \"$DATABASE_URL_BASE64\"" "$SCRIPT_DIR/whg-private/secret.yaml" | kubectl apply -f -
echo "Deploying ConfigMap..."
kubectl apply -f "$SCRIPT_DIR/configmap.yaml"

# Deploy PostgreSQL components
echo "Deploying PostgreSQL..."
kubectl apply -f "$SCRIPT_DIR/django/postgres-storage-class.yaml"
kubectl apply -f "$SCRIPT_DIR/django/postgres-pv.yaml"
kubectl apply -f "$SCRIPT_DIR/django/postgres-pvc.yaml"
kubectl apply -f "$SCRIPT_DIR/pgbackrest/pgbackrest-pv-pvc.yaml"
kubectl apply -f "$SCRIPT_DIR/django/postgres-deployment.yaml"
kubectl apply -f "$SCRIPT_DIR/django/postgres-service.yaml"
kubectl apply -f "$SCRIPT_DIR/pgbackrest/pgbackrest-cron.yaml"

## Deploy Redis
echo "Deploying Redis..."
kubectl apply -f "$SCRIPT_DIR/django/redis-pv-pvc.yaml"
kubectl apply -f "$SCRIPT_DIR/django/redis-deployment.yaml"
kubectl apply -f "$SCRIPT_DIR/django/redis-service.yaml"

# Deploy Django app
echo "Deploying Django app..."
kubectl apply -f "$SCRIPT_DIR/django/django-pv-pvc.yaml"
yq e ".spec.template.spec.volumes += [{
  \"name\": \"entrypoint-django-init\",
  \"hostPath\": {
    \"path\": \"$SCRIPT_DIR/entrypoint-django-init.sh\",
    \"type\": \"File\"
  }
}] |
.spec.template.spec.volumes += [{
  \"name\": \"whg-env-template\",
  \"hostPath\": {
    \"path\": \"$SCRIPT_DIR/whg-private/env_template.py\",
    \"type\": \"File\"
  }
}] |
.spec.template.spec.volumes += [{
  \"name\": \"whg-local-settings\",
  \"hostPath\": {
    \"path\": \"$SCRIPT_DIR/whg-private/local_settings.py\",
    \"type\": \"File\"
  }
}] |
.spec.template.spec.volumes += [{
  \"name\": \"whg-ca-cert\",
  \"hostPath\": {
    \"path\": \"$SCRIPT_DIR/whg-private/ca-cert.pem\",
    \"type\": \"File\"
  }
}] |
.spec.template.spec.containers[0].image |= sub(\"web:latest\", \"web:$IMAGE_VERSION\") |
.spec.template.spec.initContainers[0].image |= sub(\"web:latest\", \"web:$IMAGE_VERSION\") |
.spec.template.spec.initContainers[1].image |= sub(\"web:latest\", \"web:$IMAGE_VERSION\")" \
  "$SCRIPT_DIR/django/django-deployment.yaml" | kubectl apply -f -
kubectl apply -f "$SCRIPT_DIR/django/django-service.yaml"
if [ "$K8S_ENVIRONMENT" == "development" ]; then
  kubectl apply -f "$SCRIPT_DIR/django/django-ingress-local.yaml" # Serve on localhost
  kubectl port-forward svc/django-service 8000:8000 & # Run in background
else
  yq e "$YQ_TLS" "$SCRIPT_DIR/django/django-ingress.yaml" | kubectl apply -f - # Remove cert-manager and tls section for worker nodes
fi

# Wait for Django deployment to complete
echo "Waiting for Django deployment to complete..."
kubectl rollout status deployment/django -n default --timeout=600s

# Deploy Celery components
echo "Deploying Celery components..."
YQ_CONFIGURATION=".spec.template.spec.volumes += [{
  \"name\": \"whg-local-settings\",
  \"hostPath\": {
    \"path\": \"$SCRIPT_DIR/whg-private/local_settings.py\",
    \"type\": \"File\"
  }
}] |
.spec.template.spec.volumes += [{
  \"name\": \"whg-ca-cert\",
  \"hostPath\": {
    \"path\": \"$SCRIPT_DIR/whg-private/ca-cert.pem\",
    \"type\": \"File\"
  }
}] | .spec.template.spec.containers[0].image |= sub(\"web:latest\", \"web:$IMAGE_VERSION\")"
yq e "$YQ_CONFIGURATION" "$SCRIPT_DIR/django/celery-worker-deployment.yaml" | kubectl apply -f -
yq e "$YQ_CONFIGURATION" "$SCRIPT_DIR/django/celery-beat-deployment.yaml" | kubectl apply -f -
yq e "$YQ_CONFIGURATION" "$SCRIPT_DIR/django/celery-flower-deployment.yaml" | kubectl apply -f -

## Deploy Webpack
if [ "$K8S_ENVIRONMENT" == "development" ]; then
  echo "Deploying Webpack..."
  kubectl apply -f "$SCRIPT_DIR/django/webpack-pv-pvc.yaml"
  kubectl apply -f "$SCRIPT_DIR/django/webpack-config.yaml"
  kubectl apply -f "$SCRIPT_DIR/django/webpack-deployment.yaml"
fi