#!/bin/bash

# This script prepares the persistent volumes for the WHG project by syncing directories and fetching backups.
# It would typically be run on the Pitt VM, as outlined in `docs-source/content/600-Technical-Administration.md`

# Set parameters for cloning the database and tiles
CLONE_DB=false  # Default to false; set to true if you want to clone the database
CLONE_TILES=false  # Default to false; set to true if you want to clone the tiles
while [[ $# -gt 0 ]]; do
  case $1 in
    --clone-db)
      CLONE_DB="$2"
      shift 2
      ;;
    --clone-tiles)
      CLONE_TILES="$2"
      shift 2
      ;;
    *)
      echo "Unknown parameter: $1"
      exit 1
      ;;
  esac
done

BASE_DIR="/ix1/whcdh"
export K8S_ID="PITT"

# Define constants
REMOTE_USER="whgadmin"
REMOTE_HOST="144.126.204.70"
REMOTE_HOST_TILER="134.209.177.234"

# Remote directories for syncing
declare -A REMOTE_PATHS=(
  [media]="$REMOTE_USER@$REMOTE_HOST:/home/whgadmin/sites/whgazetteer-org/media"
  [static]="$REMOTE_USER@$REMOTE_HOST:/home/whgadmin/sites/whgazetteer-org/static"
)

# Extract SSH keys from Kubernetes Secret `whg-secret`
TMP_DIR=$(mktemp -d)
trap "rm -rf $TMP_DIR" EXIT

echo "Retrieving SSH private keys from Kubernetes secret..."
BASE64_DECODE() { base64 --decode 2>/dev/null || base64 -d; } # Fallback for BusyBox
kubectl get secret whg-secret -o json | jq -r '.data["id_rsa_whg"]' | BASE64_DECODE > "$TMP_DIR/id_rsa_whg"
kubectl get secret whg-secret -o json | jq -r '.data["id_rsa"]' | BASE64_DECODE > "$TMP_DIR/id_rsa"

chmod 600 "$TMP_DIR/id_rsa_whg" "$TMP_DIR/id_rsa"

SSH_KEY="$TMP_DIR/id_rsa_whg"
SSH_KEY_TILER="$TMP_DIR/id_rsa"

# Remote database backup directory
REMOTE_BACKUP_DIR="/home/whgadmin/backup/whgazetteer-org"

declare -A DIRECTORIES=(
  [redis]="$BASE_DIR/redis:1000:755:$K8S_ID"
  [django_app]="$BASE_DIR/django-app:1000:755:$K8S_ID"
  [media]="$BASE_DIR/django-media:1000:755:$K8S_ID"
  [static]="$BASE_DIR/django-static:1000:755:$K8S_ID"
  [webpack]="$BASE_DIR/webpack:1000:755:$K8S_ID"
  [tiles]="$BASE_DIR/tiles:1000:755:$K8S_ID"
  [tileserver]="$BASE_DIR/tileserver:1000:755:$K8S_ID"
  [mapdata]="$BASE_DIR/tileserver/mapdata:1000:755:$K8S_ID"
  [wordpress]="$BASE_DIR/wordpress:1001:755:$K8S_ID"
  [wordpress_data]="$BASE_DIR/wordpress-data:1001:755:$K8S_ID"
  [postgres_data]="$BASE_DIR/postgres:999:700:$K8S_ID"
  [pgbackrest]="$BASE_DIR/pgbackrest:999:700:$K8S_ID"
  [prometheus]="$BASE_DIR/prometheus:1000-65534:775:$K8S_ID"
  [grafana]="$BASE_DIR/grafana:65534:755:$K8S_ID"
  [plausible]="$BASE_DIR/plausible:1001:777:$K8S_ID"
  [clickhouse]="$BASE_DIR/clickhouse:999:777:$K8S_ID"
  [glitchtip]="$BASE_DIR/glitchtip:1001:777:$K8S_ID"
  [vespa_content_var]="$BASE_DIR/vespa-content-var:1000:755:$K8S_ID"
  [vespa_config_var_0]="$BASE_DIR/vespa-config/0/var:1000:755:$K8S_ID"
  [vespa_config_logs_0]="$BASE_DIR/vespa-config/0/logs:1000:755:$K8S_ID"
  [vespa_config_workspace_0]="$BASE_DIR/vespa-config/0/workspace:1000:755:$K8S_ID"
  [vespa_config_var_1]="$BASE_DIR/vespa-config/1/var:1000:755:$K8S_ID"
  [vespa_config_logs_1]="$BASE_DIR/vespa-config/1/logs:1000:755:$K8S_ID"
  [vespa_config_workspace_1]="$BASE_DIR/vespa-config/1/workspace:1000:755:$K8S_ID"
  [vespa_config_var_2]="$BASE_DIR/vespa-config/2/var:1000:755:$K8S_ID"
  [vespa_config_logs_2]="$BASE_DIR/vespa-config/2/logs:1000:755:$K8S_ID"
  [vespa_config_workspace_2]="$BASE_DIR/vespa-config/2/workspace:1000:755:$K8S_ID"
  [vespa_ingestion]="$BASE_DIR/vespa-ingestion:1000:755:$K8S_ID"
)

# Functions
sync_directory() {
  local remote_source="$1"
  local local_dest="$2"
  local ssh_key="$3"

  echo "Syncing $remote_source to $local_dest"
  rsync -avz -e "ssh -i $ssh_key" "$remote_source/" "$local_dest"

  # Check if rsync command was successful
  if [ $? -ne 0 ]; then
    echo "Error: Failed to sync $remote_source to $local_dest."
    return 1  # Indicate failure
  fi
}

fetch_and_extract_backup() {
  local remote_backup_dir="$1"
  local local_database_dir="$2"
  local ssh_key="$3"

  echo "Finding the latest backup file on the remote server..."
  local latest_backup_file
  latest_backup_file=$(ssh -i "$ssh_key" "$REMOTE_USER@$REMOTE_HOST" "ls -t $remote_backup_dir/*.tar.gz | head -n 1" 2>/dev/null)

  # Check if SSH command was successful and the backup file exists
  if [ $? -ne 0 ]; then
    echo "Error: Unable to connect to $REMOTE_HOST. Please check your connection."
    return 1  # Indicate failure
  elif [ -z "$latest_backup_file" ]; then
    echo "Error: No backup files found in $remote_backup_dir on $REMOTE_HOST."
    return 1  # Indicate failure
  fi

  echo "Fetching the backup file: $latest_backup_file..."
  rsync -avz -e "ssh -i $ssh_key" "$REMOTE_USER@$REMOTE_HOST:$latest_backup_file" "$local_database_dir/"
  if [ $? -ne 0 ]; then
    echo "Error: Failed to fetch the backup file."
    return 1  # Indicate failure
  fi

  local backup_filename
  backup_filename=$(basename "$latest_backup_file")
  echo "Extracting the backup file: $backup_filename..."
  tar -xzf "$local_database_dir/$backup_filename" -C "$local_database_dir"
  if [ $? -ne 0 ]; then
    echo "Error: Failed to extract the backup file."
    return 1  # Indicate failure
  fi

  # Reset ownership and permissions for the extracted backup
  IFS=":" read -r path user_group perms relevant_ids <<< "${DIRECTORIES[postgres_data]}"
  chown -R "$user_group" "$path"
  chmod -R "$perms" "$path"

  echo "Cleaning up the temporary backup file..."
  rm -f "$local_database_dir/$backup_filename"
}

prepare_directory() {
  local dir="$1"
  local user_group="$2"
  local perms="$3"

  echo "Preparing directory: $dir"

  if [[ "$user_group" == *"-"* ]]; then
    local user=$(echo "$user_group" | cut -d '-' -f 1)
    local group=$(echo "$user_group" | cut -d '-' -f 2)
  else
    local user="$user_group"
    local group="$user_group"
  fi

  mkdir -p "$dir"
  chown -R "$user:$group" "$dir"
  chmod -R "$perms" "$dir"
}

for key in "${!DIRECTORIES[@]}"; do
  IFS=":" read -r path user_group perms relevant_ids <<< "${DIRECTORIES[$key]}"
  if [[ "$relevant_ids" == *"$K8S_ID"* ]]; then
    prepare_directory "$path" "$user_group" "$perms"
  else
    echo "Skipping $key for environment <$K8S_ID>."
  fi
done

echo "All relevant directories under $BASE_DIR prepared for <$K8S_ID>."

# Sync directories if required
echo "Syncing required remote directories..."
for key in "${!REMOTE_PATHS[@]}"; do
  IFS=":" read -r local_path _ <<< "${DIRECTORIES[$key]}"

  # Check if the local directory exists before syncing
  if [ -d "$local_path" ]; then
    sync_directory "${REMOTE_PATHS[$key]}" "$local_path" "$SSH_KEY"
  else
    echo "$key not required for node <$K8S_ID>."
  fi
done

# Fetch and extract the database backup if CLONE_DB is true
if [[ -n "$CLONE_DB" && "$CLONE_DB" == "true" && -d "${DIRECTORIES[postgres_data]%%:*}" ]]; then
  fetch_and_extract_backup "$REMOTE_BACKUP_DIR" "${DIRECTORIES[postgres_data]%%:*}" "$SSH_KEY"
  export CLONE_DB=false
else
  echo "Database backup not required for node <$K8S_ID>."
fi

# Fetch and extract the map tiles if CLONE_TILES is true
if [[ -n "$CLONE_TILES" && "$CLONE_TILES" == "true" && -d "${DIRECTORIES[tiles]%%:*}" ]]; then
  sync_directory "$REMOTE_USER@$REMOTE_HOST_TILER:/srv/tileserver/tiles" "${DIRECTORIES[tiles]%%:*}" "$SSH_KEY_TILER"
  # config.json is required for mbtiles metadata; its base configuration is overwritten from the GitHub repository
  sync_directory "$REMOTE_USER@$REMOTE_HOST_TILER:/srv/tileserver/configs" "${DIRECTORIES[tileserver]%%:*}/configs" "$SSH_KEY_TILER"
  export CLONE_TILES=false
else
  echo "Map tiles backup not required for node <$K8S_ID>."
fi
