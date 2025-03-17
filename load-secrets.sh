#!/bin/bash

# To create the Django Files Secret for storage in HashiCorp Vault, run the following commands in the folder
# where the Django Files are stored, then copy-paste the output into the `data` section of the Secret definition:
# zip -j ./django-files.zip ./env_template.py ./local_settings.py
# base64 -w 0 ./django-files.zip > ./django-files.zip.base64

set -e  # Exit on error
set -o pipefail  # Catch errors in pipes

NAMESPACE_MANAGEMENT="management"
NAMESPACE_VAULT="vault-secrets-operator-system"
NAMESPACE_DEFAULT="default"

resource_exists() {
  local kind="$1"
  local name="$2"
  local namespace="$3"
  kubectl get "$kind" "$name" -n "$namespace" >/dev/null 2>&1
}

delete_resource() {
  local kind="$1"
  local name="$2"
  local namespace="$3"

  if resource_exists "$kind" "$name" "$namespace"; then
    echo "Deleting $kind $name in namespace $namespace..."
    kubectl delete "$kind" "$name" -n "$namespace" --ignore-not-found=true
    # Wait until resource is removed
    until ! resource_exists "$kind" "$name" "$namespace"; do
      echo "Waiting for $kind $name to be deleted..."
      sleep 2
    done
  fi
}

helm_release_exists() {
  helm list -n "$2" | grep -q "^$1\s"
}

delete_helm_release() {
  local release="$1"
  local namespace="$2"

  if helm_release_exists "$release" "$namespace"; then
    echo "Deleting Helm release $release in namespace $namespace..."
    helm delete "$release" -n "$namespace"

    # Wait until Helm release is removed
    until ! helm_release_exists "$release" "$namespace"; do
      echo "Waiting for Helm release $release to be deleted..."
      sleep 2
    done
  fi
}

# **1. Remove existing resources**
kubectl patch hcpvaultsecretsapp whg-secret -p '{"metadata":{"finalizers":[]}}' --type=merge
delete_helm_release "vault-secrets-operator" "$NAMESPACE_VAULT"
delete_resource "HCPAuth" "default" "$NAMESPACE_VAULT"
delete_resource "HCPVaultSecretsApp" "whg-secret" "$NAMESPACE_DEFAULT"
delete_resource "Secret" "vso-sp" "$NAMESPACE_DEFAULT"
delete_resource "Secret" "whg-secret" "$NAMESPACE_MANAGEMENT"
delete_resource "Secret" "whg-secret" "$NAMESPACE_DEFAULT"
delete_resource "Secret" "hcp-credentials" "$NAMESPACE_VAULT"

# **2. Install the HashiCorp Vault Secrets Operator**
echo "Installing the HashiCorp Vault Secrets Operator..."
helm install vault-secrets-operator ./vault-secrets-operator --namespace "$NAMESPACE_VAULT" --create-namespace

# **3. Create Kubernetes Secret for HCP Service Principal credentials**
echo "Creating Kubernetes Secret for HCP Service Principal..."
kubectl create secret generic vso-sp \
    --namespace "$NAMESPACE_DEFAULT" \
    --from-literal=clientID="$HCP_CLIENT_ID" \
    --from-literal=clientSecret="$HCP_CLIENT_SECRET" --dry-run=client -o yaml | \
kubectl apply -f -


# **4. Create HCPAuth resource for the HashiCorp Vault Secrets Operator**
echo "Creating HCPAuth resource..."
kubectl apply -f - <<EOF
apiVersion: secrets.hashicorp.com/v1beta1
kind: HCPAuth
metadata:
  name: default
  namespace: $NAMESPACE_VAULT
spec:
  organizationID: "a99eb120-dbe9-48b7-96c1-0286a81223ed"
  projectID: "be40e446-773e-4069-9913-803be758e6e8"
  servicePrincipal:
    secretRef: vso-sp
EOF

# **5. Create HCPVaultSecretsApp to fetch required secrets**
echo "Fetching required secrets from HashiCorp Vault..."
kubectl apply -f - <<EOF
apiVersion: secrets.hashicorp.com/v1beta1
kind: HCPVaultSecretsApp
metadata:
  name: whg-secret
  namespace: $NAMESPACE_DEFAULT
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
secret_exists() {
  kubectl get secret "$1" -n "$2" -o name &>/dev/null
}
until secret_exists whg-secret default; do
  echo "Waiting for whg-secret to be created..."
  sleep 2
done
echo "...whg-secret has been created."

# Ensure existence of `/whg/files/private` directory
SCRIPT_DIR="$(realpath "$(dirname "${BASH_SOURCE[0]}")")"
PRIVATE_DIR="$SCRIPT_DIR/whg/files/private"
mkdir -p "$PRIVATE_DIR"
chmod 775 "$PRIVATE_DIR"

# Fetch Secret JSON
SECRET_JSON=$(kubectl get secret whg-secret -o json)

# Extract and store secrets
echo "$SECRET_JSON" | jq -r '.data.ca_cert' | base64 -d > "$PRIVATE_DIR/ca-cert.pem"
echo "$SECRET_JSON" | jq -r '.data.django_files' | base64 -d > "$PRIVATE_DIR/django-files.zip.base64"
echo "$SECRET_JSON" | jq -r '.data.id_rsa' | base64 -d > "$PRIVATE_DIR/id_rsa"
echo "$SECRET_JSON" | jq -r '.data.id_rsa_whg' | base64 -d > "$PRIVATE_DIR/id_rsa_whg"

# Remove sensitive keys from JSON and prepare for update
SECRET_JSON=$(echo "$SECRET_JSON" | jq 'del(.data.django_files, .data.id_rsa, .data.id_rsa_whg)')

# Unzip django files
chmod 600 "$PRIVATE_DIR/django-files.zip.base64"
base64 -d "$PRIVATE_DIR/django-files.zip.base64" > "$PRIVATE_DIR/django-files.zip"
unzip -o "$PRIVATE_DIR/django-files.zip" -d "$PRIVATE_DIR"
rm -f "$PRIVATE_DIR/django-files.zip" "$PRIVATE_DIR/django-files.zip.base64"

# Set file permissions
chmod 600 "$PRIVATE_DIR/id_rsa" "$PRIVATE_DIR/id_rsa_whg"
chmod 644 "$PRIVATE_DIR/ca-cert.pem" "$PRIVATE_DIR/env_template.py" "$PRIVATE_DIR/local_settings.py"

# Encode new files and update SECRET_JSON
SECRET_JSON=$(echo "$SECRET_JSON" | jq --arg env "$(base64 -w 0 "$PRIVATE_DIR/env_template.py")" \
                                      --arg loc "$(base64 -w 0 "$PRIVATE_DIR/local_settings.py")" \
                                      '.data.env_template = $env | .data.local_settings = $loc')

# Construct DATABASE_URL
VALUES_FILE="$SCRIPT_DIR/whg/values.yaml"
DB_USER=$(yq e '.postgres.dbUser' "$VALUES_FILE")
DB_NAME=$(yq e '.postgres.dbName' "$VALUES_FILE")
POSTGRES_PORT=$(yq e '.postgres.port' "$VALUES_FILE")
DB_PASSWORD=$(echo "$SECRET_JSON" | jq -r '.data."db-password"' | base64 -d)
POSTGRES_HOST="postgres"
DATABASE_URL="postgres://${DB_USER}:${DB_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${DB_NAME}"

# Add DATABASE_URL to SECRET_JSON
SECRET_JSON=$(echo "$SECRET_JSON" | jq --arg db "$(echo -n "$DATABASE_URL" | base64 -w 0)" \
                                      '.data."database-url" = $db')

# Apply the modified secret in one atomic update
echo "$SECRET_JSON" | kubectl apply -f -

# Copy secret to other namespaces
for namespace in management monitoring tileserver whg wordpress; do
  # Create namespace if it doesn't exist
  kubectl create namespace "$namespace" --dry-run=client -o yaml | kubectl apply -f -
  kubectl get secret whg-secret -o json \
    | jq 'del(.metadata.ownerReferences) | .metadata.namespace = "'"$namespace"'"' \
    | kubectl apply -f -
done

echo "Secrets have been fetched and files stored in $PRIVATE_DIR."
ls -l "$PRIVATE_DIR"