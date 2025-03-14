#!/bin/bash

# Ensure that K8S_ID environment variable has been set
if [ -z "$K8S_ID" ]; then
  echo "Error: K8S_ID environment variable is not set. Exiting."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Define constants
REMOTE_USER="whgadmin"
REMOTE_HOST="144.126.204.70"
REMOTE_HOST_TILER="134.209.177.234"
SSH_KEY="$SCRIPT_DIR/whg/files/private/id_rsa_whg"
SSH_KEY_TILER="$SCRIPT_DIR/whg/files/private/id_rsa"

# Load values from values.yaml using yq
DJANGO_GITHUB_REPO=$(yq eval '.django.githubRepository' "$SCRIPT_DIR/whg/values.yaml")
DJANGO_GITHUB_BRANCH=$(yq eval '.django.githubBranch' "$SCRIPT_DIR/whg/values.yaml")

# Directories to sync or prepare
declare -A DIRECTORIES=(
  [redis]="/data/k8s/redis:1000:755:LOCAL,PITT1,AAU1"
  [django_app]="/data/k8s/django-app:1000:755:LOCAL,PITT1,AAU1"
  [media]="/data/k8s/django-media:1000:755:LOCAL,PITT1,AAU1"
  [static]="/data/k8s/django-static:1000:755:LOCAL,PITT1,AAU1"
  [webpack]="/data/k8s/webpack:1000:755:LOCAL,PITT1,AAU1"
  [tiles]="/data/k8s/tiles:1000:755:LOCAL,PITT1"
  [tileserver]="/data/k8s/tileserver:1000:755:LOCAL,PITT1"
  [mapdata]="/data/k8s/tileserver/mapdata:1000:755:LOCAL,PITT1"
  [wordpress]="/data/k8s/wordpress:1001:755:LOCAL,PITT1"
  [wordpress_data]="/data/k8s/wordpress-data:1001:755:LOCAL,PITT1"
  [postgres_data]="/data/k8s/postgres:999:700:LOCAL,PITT1"
  [pgbackrest]="/data/k8s/pgbackrest:999:700:LOCAL,PITT1"
  [prometheus]="/data/k8s/prometheus:1000-65534:775:LOCAL,PITT1"
  [grafana]="/data/k8s/grafana:65534:755:LOCAL,PITT1"
  [plausible]="/data/k8s/plausible:1001:777:LOCAL,PITT1"
  [clickhouse]="/data/k8s/clickhouse:999:777:LOCAL,PITT1"
  [glitchtip]="/data/k8s/glitchtip:1001:777:LOCAL,PITT1"
  [vespa_content_var]="/data/k8s/vespa-content-var:1000:755:LOCAL,PITT2"
  [vespa_config_var_0]="/data/k8s/vespa-config/0/var:1000:755:LOCAL,PITT2"
  [vespa_config_logs_0]="/data/k8s/vespa-config/0/logs:1000:755:LOCAL,PITT2"
  [vespa_config_workspace_0]="/data/k8s/vespa-config/0/workspace:1000:755:LOCAL,PITT2"
  [vespa_config_var_1]="/data/k8s/vespa-config/1/var:1000:755:LOCAL,PITT2"
  [vespa_config_logs_1]="/data/k8s/vespa-config/1/logs:1000:755:LOCAL,PITT2"
  [vespa_config_workspace_1]="/data/k8s/vespa-config/1/workspace:1000:755:LOCAL,PITT2"
  [vespa_config_var_2]="/data/k8s/vespa-config/2/var:1000:755:LOCAL,PITT2"
  [vespa_config_logs_2]="/data/k8s/vespa-config/2/logs:1000:755:LOCAL,PITT2"
  [vespa_config_workspace_2]="/data/k8s/vespa-config/2/workspace:1000:755:LOCAL,PITT2"
  [vespa_ingestion]="/data/k8s/vespa-ingestion:1000:755:LOCAL,PITT2"
)

# Remote directories for syncing
declare -A REMOTE_PATHS=(
  [media]="$REMOTE_USER@$REMOTE_HOST:/home/whgadmin/sites/whgazetteer-org/media"
  [static]="$REMOTE_USER@$REMOTE_HOST:/home/whgadmin/sites/whgazetteer-org/static"
)

# Remote database backup directory
REMOTE_BACKUP_DIR="/home/whgadmin/backup/whgazetteer-org"

# Functions
prepare_directory() {
  local dir="$1"
  local user_group="$2"
  local perms="$3"

  echo "Preparing directory: $dir"

  # If the user_group has a dash (user-group), split it
  if [[ "$user_group" == *"-"* ]]; then
    local user=$(echo "$user_group" | cut -d '-' -f 1)
    local group=$(echo "$user_group" | cut -d '-' -f 2)
  else
    local user="$user_group"
    local group="$user_group"
  fi

  sudo mkdir -p "$dir"
  sudo chown -R "$user:$group" "$dir"
  sudo chmod -R "$perms" "$dir"
}

sync_directory() {
  local remote_source="$1"
  local local_dest="$2"
  local ssh_key="$3"

  echo "Syncing $remote_source to $local_dest"
  sudo -E rsync -avz -e "ssh -i $ssh_key" --rsync-path="sudo rsync" "$remote_source/" "$local_dest"

  # Check if rsync command was successful
  if [ $? -ne 0 ]; then
    echo "Error: Failed to sync $remote_source to $local_dest."
    return  # Return to allow the script to continue execution
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
    return  # Return from function if connection fails
  elif [ -z "$latest_backup_file" ]; then
    echo "Error: No backup files found in $remote_backup_dir on $REMOTE_HOST."
    return  # Return from function if no backup files are found
  fi

  echo "Fetching the backup file: $latest_backup_file..."
  sudo -E rsync -avz -e "ssh -i $ssh_key" --rsync-path="sudo rsync" "$REMOTE_USER@$REMOTE_HOST:$latest_backup_file" "$local_database_dir/"
  if [ $? -ne 0 ]; then
    echo "Error: Failed to fetch the backup file."
    exit 1
  fi

  local backup_filename
  backup_filename=$(basename "$latest_backup_file")
  echo "Extracting the backup file: $backup_filename..."
  sudo tar -xzf "$local_database_dir/$backup_filename" -C "$local_database_dir"
  if [ $? -ne 0 ]; then
    echo "Error: Failed to extract the backup file."
    exit 1
  fi

  # Reset ownership and permissions for the extracted backup
  IFS=":" read -r path user_group perms relevant_ids <<< "${DIRECTORIES[postgres_data]}"
  sudo chown -R "$user_group" "$path"
  sudo chmod -R "$perms" "$path"

  echo "Cleaning up the temporary backup file..."
  sudo rm -f "$local_database_dir/$backup_filename"
}

# Clone the Git repository into the correct directory (from DIRECTORIES)
clone_django_repo() {
  echo "Forcefully cloning the Django repository..."

  # Extract the path for the django_app directory from DIRECTORIES
  local django_app_dir
  django_app_dir=$(echo "${DIRECTORIES[django_app]}" | cut -d ':' -f 1)

  # Check if the directory is already a Git repository
  if [ -d "$django_app_dir/.git" ]; then
    echo "The directory $django_app_dir is already a Git repository. Skipping clone."
  else
    echo "Cloning the Django repository..."

    if [ -d "$django_app_dir" ]; then
      echo "Removing existing contents of $django_app_dir..."
      sudo rm -rf "$django_app_dir"/*
    fi

    git clone -b "$DJANGO_GITHUB_BRANCH" "https://github.com/$DJANGO_GITHUB_REPO.git" "$django_app_dir" || { echo 'Cloning failed'; exit 1; }
    echo "Repository cloned successfully."
  fi
}

# Prepare directories based on K8S_ID
echo "Preparing local directories based on K8S_ID..."
for key in "${!DIRECTORIES[@]}"; do
  IFS=":" read -r path user_group perms relevant_ids <<< "${DIRECTORIES[$key]}"

  # Check if the K8S_ID is in the list of valid IDs for this directory
  if [[ "$relevant_ids" == *"$K8S_ID"* ]]; then
    prepare_directory "$path" "$user_group" "$perms"
  else
    echo "Skipping directory $key as $K8S_ID is not listed in <$relevant_ids>."
  fi
done

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

clone_django_repo

# Notes for manual steps
echo "NOTE: Wordpress database migration must be done manually."

echo "Script completed successfully."
