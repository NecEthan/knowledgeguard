.PHONY: help \
        dev dev-build dev-infra dev-down \
        test-infra test-infra-down test-backend test-frontend \
        prod prod-build prod-down

# ─── Dev ─────────────────────────────────────────────────────────────────────
# Full stack (backend + worker + frontend) with hot-reload source mounts.
# OPENAI_API_KEY must be set in .env.dev

dev:
	docker compose --env-file .env.dev up

dev-build:
	docker compose --env-file .env.dev up --build

# Infra only — use when running backend/frontend locally outside Docker
dev-infra:
	docker compose --env-file .env.dev up -d postgres redis minio minio-init

dev-down:
	docker compose --env-file .env.dev down

# ─── Test ─────────────────────────────────────────────────────────────────────
# Isolated infra on separate ports (5435/6380/9012).
# DB: knowledgeguard_test   Volumes: kg_test_*

test-infra:
	docker compose -f docker-compose.test.yml -p kg_test up -d

test-infra-down:
	docker compose -f docker-compose.test.yml -p kg_test down

# Run backend integration tests against the test DB
test-backend:
	cd backend && ENV_FILE=$(PWD)/.env.test uv run pytest tests/ -v

# Run frontend unit tests
test-frontend:
	cd frontend && npm test -- --watchAll=false --ci

# ─── Prod ─────────────────────────────────────────────────────────────────────
# Full stack, no source mounts, production frontend build.
# Requires .env.prod with real SECRET_KEY and OPENAI_API_KEY.
# Ports: backend 8002, frontend 3002, postgres 5436

prod:
	docker compose -f docker-compose.prod.yml --env-file .env.prod up

prod-build:
	docker compose -f docker-compose.prod.yml --env-file .env.prod up --build

prod-down:
	docker compose -f docker-compose.prod.yml down

# ─── Help ─────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "Dev   (ports 8000/3000/5434):  make dev | make dev-infra | make dev-down"
	@echo "Test  (ports 8001/3001/5435):  make test-infra | make test-backend | make test-frontend | make test-infra-down"
	@echo "Prod  (ports 8002/3002/5436):  make prod | make prod-build | make prod-down"
	@echo ""
	@echo "First time: copy OPENAI_API_KEY into .env.dev and .env.prod"
	@echo "Prod only:  set a real SECRET_KEY in .env.prod (openssl rand -hex 32)"
	@echo ""
