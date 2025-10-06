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
SECRET_NAMESPACE="whg"
#COPY_TO_NAMESPACES=(management monitoring tileserver whg wordpress)

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
WORDPRESS_DB_HOST=$(get_secret "wordpress-db-host")
WORDPRESS_DB_USER=$(get_secret "wordpress-db-user")
WORDPRESS_DB_PASSWORD=$(get_secret "wordpress-db-password")
WORDPRESS_DB_NAME=$(get_secret "wordpress-db-name")
DO_API_TOKEN=$(get_secret "digitalocean-pat")
UNIX_PASSWORD=$(get_secret "unix-password")

# === Construct DATABASE_URL ===
VALUES_FILE="$SCRIPT_DIR/values.yaml"
DB_USER=$(yq e '.postgres.dbUser' "$VALUES_FILE")
DB_NAME=$(yq e '.postgres.dbName' "$VALUES_FILE")
POSTGRES_PORT=$(yq e '.postgres.port' "$VALUES_FILE")
DATABASE_URL="postgres://${DB_USER}:${DB_PASSWORD}@postgres:${POSTGRES_PORT}/${DB_NAME}"

# === Create Kubernetes Secret ===
echo "🔐 Creating/updating $SECRET_NAME secret in $SECRET_NAMESPACE..."

kubectl apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: $SECRET_NAME
  namespace: $SECRET_NAMESPACE
type: Opaque
data:
  secret-key: $(echo -n "$DJANGO_SECRET_KEY" | base64)
  db-password: $(echo -n "$DB_PASSWORD" | base64)
  postgresql-admin-password: $(echo -n "$PG_ADMIN_PASSWORD" | base64)
  postgresql-user-password: $(echo -n "$PG_USER_PASSWORD" | base64)
  postgresql-replication-password: $(echo -n "$PG_REPL_PASSWORD" | base64)
  wordpress-db-host: $(echo -n "$WORDPRESS_DB_HOST" | base64)
  wordpress-db-user: $(echo -n "$WORDPRESS_DB_USER" | base64)
  wordpress-db-password: $(echo -n "$WORDPRESS_DB_PASSWORD" | base64)
  wordpress-db-name: $(echo -n "$WORDPRESS_DB_NAME" | base64)
  kubernetes-cluster-issuer: $(echo -n "$DO_API_TOKEN" | base64)
  user-password: $(echo -n "$UNIX_PASSWORD" | base64)
  database-url: $(echo -n "$DATABASE_URL" | base64)
  ca_cert: $(base64 -w0 "$TARGET_DIR/ca-cert.pem")
  env_template.py: $(base64 -w0 "$TARGET_DIR/env_template.py")
  local_settings.py: $(base64 -w0 "$TARGET_DIR/local_settings.py")
  id_rsa: $(base64 -w0 "$TARGET_DIR/id_rsa")
  id_rsa_whg: $(base64 -w0 "$TARGET_DIR/id_rsa_whg")
EOF

echo "✅ Secret '$SECRET_NAME' created."

## === Copy the secret to other namespaces ===
#echo "📦 Copying $SECRET_NAME to other namespaces..."
#for ns in "${COPY_TO_NAMESPACES[@]}"; do
#  # ensure namespace exists
#  kubectl create namespace "$ns" --dry-run=client -o yaml | kubectl apply -f -
#
#  # get secret JSON, clear fields that prevent overwrite
#  kubectl get secret "$SECRET_NAME" -n "$SECRET_NAMESPACE" -o json \
#    | jq "del(.metadata.ownerReferences, .metadata.resourceVersion, .metadata.uid) | .metadata.namespace = \"$ns\"" \
#    | kubectl apply -f -
#done
#echo "✅ Secret '$SECRET_NAME' copied to namespaces."

echo "📁 Files stored in: $TARGET_DIR"
ls -l "$TARGET_DIR"

