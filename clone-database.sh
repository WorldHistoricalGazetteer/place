#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Define variables
REMOTE_USER="whgadmin"
REMOTE_HOST="144.126.204.70"
REMOTE_BACKUP_DIR="/home/whgadmin/backup/whgazetteer-org"
LOCAL_DATABASE_DIR="/data/k8s/postgres"
LOCAL_DATABASE_BACKUP_DIR="/data/k8s/pgbackrest"
SSH_KEY="$SCRIPT_DIR/whg-private/id_rsa_whg"

# Prepare the local directories
sudo mkdir -p "$LOCAL_DATABASE_DIR"
sudo chown -R 999:999 "$LOCAL_DATABASE_DIR"
sudo chmod 700 "$LOCAL_DATABASE_DIR"
sudo mkdir -p "$LOCAL_DATABASE_BACKUP_DIR"
sudo chown -R 999:999 "$LOCAL_DATABASE_BACKUP_DIR"
sudo chmod 700 "$LOCAL_DATABASE_BACKUP_DIR"

# Find the most recent backup file
echo "Finding the latest backup file on the remote server..."
LATEST_BACKUP_FILE=$(ssh -i "$SSH_KEY" "$REMOTE_USER@$REMOTE_HOST" "ls -t $REMOTE_BACKUP_DIR/*.tar.gz | head -n 1")
if [ -z "$LATEST_BACKUP_FILE" ]; then
    echo "Error: No backup files found in $REMOTE_BACKUP_DIR on $REMOTE_HOST."
    exit 1
fi

# Fetch the latest backup
echo "Fetching the backup file: $LATEST_BACKUP_FILE..."
sudo -E rsync -avz -e "ssh -i $SSH_KEY" --rsync-path="sudo rsync" "$REMOTE_USER@$REMOTE_HOST:$LATEST_BACKUP_FILE" "$LOCAL_DATABASE_DIR/"
if [ $? -ne 0 ]; then
    echo "Error: Failed to fetch the backup file."
    exit 1
fi

# Extract the backup
BACKUP_FILENAME=$(basename "$LATEST_BACKUP_FILE")
echo "Extracting the backup file: $BACKUP_FILENAME..."
sudo tar -xzf "$LOCAL_DATABASE_DIR/$BACKUP_FILENAME" -C "$LOCAL_DATABASE_DIR"
if [ $? -ne 0 ]; then
    echo "Error: Failed to extract the backup file."
    exit 1
fi

# Clean up
echo "Cleaning up the temporary backup file..."
sudo rm -f "$LOCAL_DATABASE_DIR/$BACKUP_FILENAME"

echo "Database cloning completed successfully!"