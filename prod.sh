#!/bin/bash
set -e

docker compose -f docker-compose.prod.yml --env-file .env.prod -p kg_prod up -d

echo "Waiting for backend..."
until docker compose -f docker-compose.prod.yml -p kg_prod exec -T backend echo "ready" > /dev/null 2>&1; do
  sleep 1
done

echo "Running migrations..."
docker compose -f docker-compose.prod.yml -p kg_prod exec -T backend uv run alembic upgrade head

docker compose -f docker-compose.prod.yml -p kg_prod logs -f
