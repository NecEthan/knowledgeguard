#!/bin/bash
set -e

docker compose --env-file .env.dev up -d

echo "Waiting for backend..."
until docker compose --env-file .env.dev exec -T backend echo "ready" > /dev/null 2>&1; do
  sleep 1
done

echo "Running migrations..."
docker compose --env-file .env.dev exec -T backend uv run alembic upgrade head

docker compose --env-file .env.dev logs -f
