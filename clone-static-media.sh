#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REMOTE_USER="whgadmin"
REMOTE_HOST="144.126.204.70"
REMOTE_MEDIA_DIR="~/sites/whgazetteer-org/media"
REMOTE_STATIC_DIR="~/sites/whgazetteer-org/static"
SSH_KEY="$SCRIPT_DIR/keys/id_rsa_whg"
LOCAL_REDIS_DIR="/data/k8s/redis"
LOCAL_APP_DIR="/data/k8s/django-app"
LOCAL_MEDIA_DIR="/data/k8s/django-media"
LOCAL_STATIC_DIR="/data/k8s/django-static"

sudo mkdir -p "$LOCAL_REDIS_DIR"
sudo chown -R 1000:1000 "$LOCAL_REDIS_DIR"
sudo chmod -R 755 "$LOCAL_REDIS_DIR"
sudo mkdir -p "$LOCAL_APP_DIR"
sudo chown -R 1000:1000 "$LOCAL_APP_DIR"
sudo chmod -R 755 "$LOCAL_APP_DIR"
sudo mkdir -p "$LOCAL_MEDIA_DIR"
sudo chown -R 1000:1000 "$LOCAL_MEDIA_DIR"
sudo chmod -R 755 "$LOCAL_MEDIA_DIR"
sudo mkdir -p "$LOCAL_STATIC_DIR"
sudo chown -R 1000:1000 "$LOCAL_STATIC_DIR"
sudo chmod -R 755 "$LOCAL_STATIC_DIR"

sudo -E rsync -avz -e "ssh -i $SSH_KEY" --rsync-path="sudo rsync" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_MEDIA_DIR" "$LOCAL_MEDIA_DIR/"
sudo -E rsync -avz -e "ssh -i $SSH_KEY" --rsync-path="sudo rsync" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_STATIC_DIR" "$LOCAL_STATIC_DIR/"