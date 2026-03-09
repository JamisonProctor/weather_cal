#!/bin/bash
# Pull latest code, rebuild images, and restart containers.
# Run this on whichever machine is hosting Docker.

set -e

cd "$(dirname "$0")"

echo "Pulling latest code..."
git pull

echo "Rebuilding all images (including profiled services)..."
docker compose --profile event-worker build

echo "Restarting containers..."
docker compose up -d

echo "Done. Running containers:"
docker compose ps
