#!/bin/bash
# Pull latest code, rebuild images, and restart containers.
# Run this on whichever machine is hosting Docker.

set -e

cd "$(dirname "$0")"

echo "Pulling latest code..."
git pull

echo "Rebuilding and restarting containers..."
docker compose up --build -d

echo "Done. Running containers:"
docker compose ps
