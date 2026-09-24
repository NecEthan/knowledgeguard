#!/bin/bash
set -e

docker compose -f docker-compose.test.yml --env-file .env.test -p kg_test up -d

echo "Waiting for backend..."
until docker compose -f docker-compose.test.yml -p kg_test exec -T backend echo "ready" > /dev/null 2>&1; do
  sleep 1
done

echo "Running migrations..."
docker compose -f docker-compose.test.yml -p kg_test exec -T backend uv run alembic upgrade head

docker compose -f docker-compose.test.yml -p kg_test logs -f
