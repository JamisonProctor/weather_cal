#!/bin/bash
set -e

CONTAINER_NAME=weather-cal
VOLUME_NAME=weather_cal_data

echo "🔹 Stopping and removing container..."
docker stop $CONTAINER_NAME 2>/dev/null || true
docker rm $CONTAINER_NAME 2>/dev/null || true

echo "🔹 Removing old image..."
docker rmi $CONTAINER_NAME 2>/dev/null || true

echo "🔹 Removing old volume..."
docker volume rm $VOLUME_NAME 2>/dev/null || true

echo "🔹 Creating fresh volume and fixing permissions..."
docker volume create --name $VOLUME_NAME
docker run --rm -v $VOLUME_NAME:/data alpine sh -c "chown -R 65532:65532 /data"

echo "🔹 Rebuilding image..."
docker build --no-cache -t $CONTAINER_NAME .

echo "🔹 Starting container..."
docker run -d \
  --name $CONTAINER_NAME \
  --restart unless-stopped \
  --env-file .env \
  -v $VOLUME_NAME:/app/data \
  -v $(pwd)/credentials.json:/app/credentials.json \
  -v $(pwd)/token.json:/app/token.json \
  $CONTAINER_NAME

echo "✅ Redeployment complete."
echo "Container status:"
docker ps --filter "name=$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo "Last 5 log lines:"
docker logs --tail 5 $CONTAINER_NAME