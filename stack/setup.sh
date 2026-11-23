#!/usr/bin/env bash

# Creates the folders and starter files the containers expect. Safe to run again.

set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env. Fill in the camera details, then run ./setup.sh again."
  exit 1
fi

if grep -q change_me .env; then
  echo ".env still has change_me values. Fill them in, then run ./setup.sh again."
  exit 1
fi

mkdir -p homeassistant/www/potty homeassistant/packages poop-checker/data \
  frigate/media mosquitto/data adguard/work adguard/conf one-kvm-data

for f in automations.yaml scenes.yaml; do
  [ -f "homeassistant/$f" ] || echo "[]" > "homeassistant/$f"
done
[ -f homeassistant/scripts.yaml ] || : > homeassistant/scripts.yaml

echo "Ready. Next: docker compose up -d"
