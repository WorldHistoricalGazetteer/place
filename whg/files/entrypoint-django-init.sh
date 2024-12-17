#!/bin/bash
set -e

cd /app

# Git Sync
git fetch origin
git reset --hard origin/main

# Collect Static Files
cp --force ./env_template.py ./server-admin/env_template.py
python ./server-admin/load_env.py
python manage.py collectstatic --no-input
