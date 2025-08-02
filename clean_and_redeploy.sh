#!/bin/bash
set -e

echo "🔹 Force removing any existing containers named weather-cal..."
docker rm -f weather-cal 2>/dev/null || true

echo "🔹 Stopping and removing containers + volumes (clean start)..."
docker compose down -v || true

echo "🔹 Rebuilding image and starting fresh containers..."
docker compose up --build -d

echo "✅ Redeployment complete. Active containers:"
docker ps --filter "name=weather-cal" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo "🔹 Showing last 20 log lines..."
docker compose logs --tail=20