#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REMOTE_USER="whgadmin"
REMOTE_HOST="144.126.204.70"
REMOTE_HOST_TILER="134.209.177.234"
REMOTE_MEDIA_DIR="/home/whgadmin/sites/whgazetteer-org/media"
REMOTE_STATIC_DIR="/home/whgadmin/sites/whgazetteer-org/static"
REMOTE_TILES_DIR="/srv/tileserver/tiles"
REMOTE_TILES_CONFIG_DIR="/srv/tileserver/configs"
REMOTE_WORDPRESS_DIR="/home/whgadmin/sites/blog-whgazetteer-org"
SSH_KEY="$SCRIPT_DIR/whg-private/id_rsa_whg"
SSH_KEY_TILER="$SCRIPT_DIR/whg-private/id_rsa"
LOCAL_REDIS_DIR="/data/k8s/redis"
LOCAL_APP_DIR="/data/k8s/django-app"
LOCAL_MEDIA_DIR="/data/k8s/django-media"
LOCAL_STATIC_DIR="/data/k8s/django-static"
LOCAL_WEBPACK_DIR="/data/k8s/webpack"
LOCAL_TILES_DIR="/data/k8s/tiles"
LOCAL_WORDPRESS_DIR="/data/k8s/wordpress"
LOCAL_WORDPRESS_DATA_DIR="/data/k8s/wordpress-data"

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
sudo mkdir -p "$LOCAL_WEBPACK_DIR"
sudo chown -R 1000:1000 "$LOCAL_WEBPACK_DIR"
sudo chmod -R 755 "$LOCAL_WEBPACK_DIR"
sudo mkdir -p "$LOCAL_TILES_DIR"
sudo chown -R 1000:1000 "$LOCAL_TILES_DIR"
sudo chmod -R 755 "$LOCAL_TILES_DIR"
sudo mkdir -p "$LOCAL_WORDPRESS_DIR"
sudo chown -R 1001:1001 "$LOCAL_WORDPRESS_DIR"
sudo chmod -R 755 "$LOCAL_WORDPRESS_DIR"
sudo mkdir -p "$LOCAL_WORDPRESS_DATA_DIR"
sudo chown -R 1001:1001 "$LOCAL_WORDPRESS_DATA_DIR"
sudo chmod -R 755 "$LOCAL_WORDPRESS_DATA_DIR"

sudo -E rsync -avz -e "ssh -i $SSH_KEY" --rsync-path="sudo rsync" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_MEDIA_DIR/" "$LOCAL_MEDIA_DIR"
sudo -E rsync -avz -e "ssh -i $SSH_KEY" --rsync-path="sudo rsync" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_STATIC_DIR/" "$LOCAL_STATIC_DIR"


sudo -E rsync -avz -e "ssh -i $SSH_KEY" --rsync-path="sudo rsync" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_STATIC_DIR/" "$LOCAL_STATIC_DIR"

# Do not clone Wordpress database because the Helm version uses MariaDB as opposed to MySQL on the old server. Content should be migrated manually.

# If you use the following rsync, you will need to upgrade the config.json format from Tileserver GL Light to Tileserver GL
# This means adding "serve_rendered": false to all of the vector style definitions, and changing the paths as follows:

#        "paths": {
#          "root": "../../",
#          "fonts": "./assets/fonts",
#          "sprites": "./assets/sprites",
#          "icons": "./assets/icons",
#          "styles": "./assets/styles",
#          "mbtiles": "./tiles",
#          "files": "./assets/files",
#          "images": "./public/resources/images"
#        }

#sudo rsync -avz -e "ssh -i $SSH_KEY_TILER" "$REMOTE_USER@$REMOTE_HOST_TILER:$REMOTE_TILES_CONFIG_DIR/" "$LOCAL_TILES_DIR/configs"
