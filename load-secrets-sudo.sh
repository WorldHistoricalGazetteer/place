#!/bin/bash

# To create the Django Files Secret for storage in HashiCorp Vault, run the following commands in the folder
# where the Django Files are stored, then copy-paste the output into the `data` section of the Secret definition:
# sudo zip -j ./django-files.zip ./env_template.py ./local_settings.py
# sudo base64 -w 0 ./django-files.zip > ./django-files.zip.base64

# Install the HashiCorp Vault Secrets Operator
echo "Installing the HashiCorp Vault Secrets Operator..."
helm install vault-secrets-operator ./vault-secrets-operator --namespace vault-secrets-operator-system --create-namespace

# Create Secret for HashiCorp Cloud Platform (HCP) Service Principal credentials (these should already be set as environment variables)
echo "Creating Kubernetes Secret for HashiCorp Cloud Platform Service Principal credentials..."
kubectl create secret generic vso-sp \
    --namespace default \
    --from-literal=clientID=$HCP_CLIENT_ID \
    --from-literal=clientSecret=$HCP_CLIENT_SECRET

# Create HCPAuth resource for the HashiCorp Vault Secrets Operator
echo "Creating HCPAuth resource for the HashiCorp Vault Secrets Operator..."
kubectl create -f - <<EOF
---
apiVersion: secrets.hashicorp.com/v1beta1
kind: HCPAuth
metadata:
  name: default
  namespace: vault-secrets-operator-system
spec:
  organizationID: "a99eb120-dbe9-48b7-96c1-0286a81223ed"
  projectID: "be40e446-773e-4069-9913-803be758e6e8"
  servicePrincipal:
    secretRef: vso-sp
EOF

# Fetch required Secrets from HashiCorp Vault
kubectl create -f - <<EOF
apiVersion: secrets.hashicorp.com/v1beta1
kind: HCPVaultSecretsApp
metadata:
  name: whg-secret
  namespace: default
spec:
  appName: "WHG-PLACE"
  destination:
    create: true
    labels:
      hvs: "true"
    name: whg-secret
    transformation:
      excludes:
        - .*
      excludeRaw: true
      templates:
        ca_cert:
          text: >
            {{ get ((get .Secrets "Certificates") | fromJson) "ca-cert.pem" }}
        django_files:
          text: >
            {{ get .Secrets "Django_Files" }}
        id_rsa:
          text: >
            {{ get (get ((get .Secrets "Keys") | fromJson) "DO_Main") "id_rsa" }}
        id_rsa_whg:
          text: >
            {{ get (get ((get .Secrets "Keys") | fromJson) "DO_Tileserver") "id_rsa_whg" }}
        user-password:
          text: >
            {{ get ((get .Secrets "Server_Settings") | fromJson) "unix-password" }}
        secret-key:
          text: "Redundant? Included in Django_Variables"
        kubernetes-cluster-issuer:
          text: >
            {{ get (get ((get .Secrets "Digital_Ocean") | fromJson) "API Access") "Personal Access Token" }}
        db-password:
          text: >
            {{ get ((get .Secrets "Server_Settings") | fromJson) "django-postgres-password" }}
        postgres-password:
          text: >
            {{ get ((get .Secrets "Server_Settings") | fromJson) "postgresql-admin-password" }}
        postgresql-admin-password:
          text: >
            {{ get ((get .Secrets "Server_Settings") | fromJson) "postgresql-admin-password" }}
        postgresql-user-password:
          text: >
            {{ get ((get .Secrets "Server_Settings") | fromJson) "postgresql-user-password" }}
        postgresql-replication-password:
          text: >
            {{ get ((get .Secrets "Server_Settings") | fromJson) "postgresql-replication-password" }}
EOF

# Wait for creation of the Secret
until kubectl get secret whg-secret -n default; do
  echo "Waiting for whg-secret to be created..."
  sleep 2
done
echo "...whg-secret has been created."

# Ensure existence of `/whg/files/private` directory; create files from secrets
PRIVATE_DIR="$SCRIPT_DIR/whg/files/private"
sudo mkdir -p "$PRIVATE_DIR"
chmod 775 "$PRIVATE_DIR"
kubectl get secret whg-secret -o jsonpath='{.data.ca_cert}' | base64 --decode > "$PRIVATE_DIR/ca-cert.pem"
kubectl get secret whg-secret -o jsonpath='{.data.django_files}' | base64 --decode > "$PRIVATE_DIR/django-files.zip.base64"
kubectl patch secret whg-secret -p '{"data": {"django_files": null}}'
chmod 600 "$PRIVATE_DIR/django-files.zip.base64"
base64 --decode "$PRIVATE_DIR/django-files.zip.base64" > "$PRIVATE_DIR/django-files.zip"
unzip -o "$PRIVATE_DIR/django-files.zip" -d "$PRIVATE_DIR"
sudo rm -f "$PRIVATE_DIR/django-files.zip"
sudo rm -f "$PRIVATE_DIR/django-files.zip.base64"
kubectl get secret whg-secret -o jsonpath='{.data.id_rsa}' | base64 --decode > "$PRIVATE_DIR/id_rsa"
kubectl patch secret whg-secret -p '{"data": {"id_rsa": null}}'
kubectl get secret whg-secret -o jsonpath='{.data.id_rsa_whg}' | base64 --decode > "$PRIVATE_DIR/id_rsa_whg"
kubectl patch secret whg-secret -p '{"data": {"id_rsa_whg": null}}'

chmod 600 "$PRIVATE_DIR/id_rsa"
chmod 600 "$PRIVATE_DIR/id_rsa_whg"
chmod 644 "$PRIVATE_DIR/ca-cert.pem"
chmod 644 "$PRIVATE_DIR/env_template.py"
chmod 644 "$PRIVATE_DIR/local_settings.py"

# Add these unzipped files back into the Secret
kubectl patch secret whg-secret -p '{"data": {"env_template": "'$(base64 -w 0 "$PRIVATE_DIR/env_template.py")'"}}'
kubectl patch secret whg-secret -p '{"data": {"local_settings": "'$(base64 -w 0 "$PRIVATE_DIR/local_settings.py")'"}}'

# Construct and add DATABASE_URL
VALUES_FILE="$SCRIPT_DIR/whg/values.yaml"
DB_USER=$(yq e '.postgres.dbUser' "$VALUES_FILE")
DB_NAME=$(yq e '.postgres.dbName' "$VALUES_FILE")
POSTGRES_PORT=$(yq e '.postgres.port' "$VALUES_FILE")
DB_PASSWORD=$(kubectl get secret whg-secret -o jsonpath='{.data.db-password}' | base64 --decode)
POSTGRES_HOST="postgres"
DATABASE_URL="postgres://${DB_USER}:${DB_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${DB_NAME}"
kubectl patch secret whg-secret -p '{"data": {"database-url": "'$(echo -n "$DATABASE_URL" | base64 -w 0)'"}}'

# Copy secret to other namespaces
for namespace in whg monitoring tileserver wordpress; do
  kubectl create namespace $namespace
  kubectl get secret whg-secret -o json \
    | jq 'del(.metadata.ownerReferences) | .metadata.namespace = "'"$namespace"'"' \
    | kubectl apply -f -
done

echo "Secrets have been fetched and files stored in $PRIVATE_DIR."
ls -l "$PRIVATE_DIR"