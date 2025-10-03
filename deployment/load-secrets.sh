#!/bin/bash

# This is normally called through deployment/templates/management-deployment.yaml

set -euo pipefail

# === Config ===
GITHUB_REPO="github.com/WorldHistoricalGazetteer/secrets"
TEMP_SECRETS_DIR="$(mktemp -d)"
SCRIPT_DIR="$(realpath "$(dirname "${BASH_SOURCE[0]}")")"
TARGET_DIR="$SCRIPT_DIR/whg/files/private"
MISC_FILE="$TEMP_SECRETS_DIR/miscellaneous/place.md"
SECRET_NAME="whg-secret"
SECRET_NAMESPACE="default"
COPY_TO_NAMESPACES=(management monitoring tileserver whg wordpress)

# === Ensure cleanup of temporary directory ===
cleanup() {
  rm -rf "$TEMP_SECRETS_DIR"
}
trap cleanup EXIT

# === Ensure target directory exists ===
mkdir -p "$TARGET_DIR"
chmod 775 "$TARGET_DIR"

# === Clone secrets repo ===
if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "❌ GITHUB_TOKEN not set"
  exit 1
fi

echo "⬇️ Cloning secrets repo into $TEMP_SECRETS_DIR..."
git clone --depth 1 "https://x-access-token:$GITHUB_TOKEN@$GITHUB_REPO" "$TEMP_SECRETS_DIR"

# === Copy Django config and key files ===
cp "$TEMP_SECRETS_DIR/django/env_template.py" "$TARGET_DIR/"
cp "$TEMP_SECRETS_DIR/django/local_settings.py" "$TARGET_DIR/"
cp "$TEMP_SECRETS_DIR/keys/ca-cert.pem" "$TARGET_DIR/"
cp "$TEMP_SECRETS_DIR/keys/id_rsa" "$TARGET_DIR/"
cp "$TEMP_SECRETS_DIR/keys/id_rsa_whg" "$TARGET_DIR/"
chmod 600 "$TARGET_DIR/id_rsa" "$TARGET_DIR/id_rsa_whg"
chmod 644 "$TARGET_DIR/ca-cert.pem" "$TARGET_DIR/env_template.py" "$TARGET_DIR/local_settings.py"

# === Function to extract secret from markdown block ===
get_secret() {
  awk "/^## $1\$/ {getline; getline; print}" "$MISC_FILE"
}

# === Extract secrets from markdown ===
DJANGO_SECRET_KEY=$(get_secret "django-secret-key")
DB_PASSWORD=$(get_secret "django-postgres-password")
PG_ADMIN_PASSWORD=$(get_secret "postgresql-admin-password")
PG_USER_PASSWORD=$(get_secret "postgresql-user-password")
PG_REPL_PASSWORD=$(get_secret "postgresql-replication-password")
DO_API_TOKEN=$(get_secret "digitalocean-pat")
UNIX_PASSWORD=$(get_secret "unix-password")

# === Construct DATABASE_URL ===
VALUES_FILE="$HOME/deployment-repo/values.yaml"
DB_USER=$(yq e '.postgres.dbUser' "$VALUES_FILE")
DB_NAME=$(yq e '.postgres.dbName' "$VALUES_FILE")
POSTGRES_PORT=$(yq e '.postgres.port' "$VALUES_FILE")
DATABASE_URL="postgres://${DB_USER}:${DB_PASSWORD}@postgres:${POSTGRES_PORT}/${DB_NAME}"

# === Create Kubernetes Secret ===
echo "🔐 Creating/updating $SECRET_NAME secret in $SECRET_NAMESPACE..."
kubectl create secret generic "$SECRET_NAME" \
  --namespace "$SECRET_NAMESPACE" \
  --from-literal=secret-key="$DJANGO_SECRET_KEY" \
  --from-literal=db-password="$DB_PASSWORD" \
  --from-literal=postgres-password="$PG_ADMIN_PASSWORD" \
  --from-literal=postgresql-admin-password="$PG_ADMIN_PASSWORD" \
  --from-literal=postgresql-user-password="$PG_USER_PASSWORD" \
  --from-literal=postgresql-replication-password="$PG_REPL_PASSWORD" \
  --from-literal=kubernetes-cluster-issuer="$DO_API_TOKEN" \
  --from-literal=user-password="$UNIX_PASSWORD" \
  --from-literal=database-url="$DATABASE_URL" \
  --from-file=ca_cert="$TARGET_DIR/ca-cert.pem" \
  --from-file=env_template.py="$TARGET_DIR/env_template.py" \
  --from-file=local_settings.py="$TARGET_DIR/local_settings.py" \
  --from-file=id_rsa="$TARGET_DIR/id_rsa" \
  --from-file=id_rsa_whg="$TARGET_DIR/id_rsa_whg" \
  --dry-run=client -o yaml | kubectl apply -f -

# === Copy the secret to other namespaces ===
echo "📦 Copying $SECRET_NAME to other namespaces..."
for ns in "${COPY_TO_NAMESPACES[@]}"; do
  kubectl create namespace "$ns" --dry-run=client -o yaml | kubectl apply -f -
  kubectl get secret "$SECRET_NAME" -n "$SECRET_NAMESPACE" -o json \
    | jq 'del(.metadata.ownerReferences) | .metadata.namespace = "'"$ns"'"' \
    | kubectl apply -f -
done

echo "✅ Secret '$SECRET_NAME' created and copied to namespaces."
echo "📁 Files stored in: $TARGET_DIR"
ls -l "$TARGET_DIR"

