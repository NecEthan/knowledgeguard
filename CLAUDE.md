# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

KnowledgeGuard is an AI-powered enterprise knowledge platform. Employees upload company documents; the system chunks and embeds them, then answers natural-language questions with citations to the source document and version.

## Monorepo Layout

```
knowledgeguard/
├── backend/          FastAPI service (Python, uv)
├── frontend/         Next.js 14 app (TypeScript, npm)
├── playwright-tests/ E2E tests (Playwright, npm)
├── docs/             Design docs
└── docker-compose.yml  Infrastructure: PostgreSQL, Redis, MinIO
```

## Commands

### Infrastructure

```bash
docker compose up -d          # Start postgres (port 5434), Redis, MinIO
docker compose up -d postgres # Start only postgres (sufficient for backend integration tests)
```

### Backend

```bash
cd backend
uv sync --extra dev                          # Install all deps including dev
uv run uvicorn app.main:app --reload         # Dev server — http://localhost:8000
uv run ruff check .                          # Lint
uv run ruff format .                         # Format
uv run pytest tests/ -v                                                          # All tests
uv run pytest tests/routers/test_documents.py -v                                 # Single test file
uv run pytest tests/routers/test_documents.py::test_upload_creates_db_records -v # Single test
```

**Integration tests** require postgres running (`docker compose up -d postgres`). MinIO and Redis are mocked. Tests connect to `postgresql+asyncpg://postgres:postgres@localhost:5434/knowledgeguard`.

**Alembic** (run inside the backend container):

```bash
docker exec knowledgeguard-backend-1 uv run alembic revision --autogenerate -m "description"
docker exec knowledgeguard-backend-1 uv run alembic upgrade head
```

### Frontend

```bash
cd frontend
npm install
npm run dev             # Dev server — http://localhost:3000
npm run lint            # ESLint
npm run format          # Prettier (write)
npm run format:check    # Prettier (check only)
npm test                # Jest (all)
npm test -- --testPathPattern=client  # Single test file
```

### E2E Tests

```bash
cd playwright-tests
npm test                # Headless
npm run test:headed     # Visible browser
npm run test:ui         # Interactive Playwright UI
```

Requires all services running. Auth state is persisted to `.auth/user.json` by `utils/auth.setup.ts` and reused by the `authenticated` project. Two Playwright projects: `unauthenticated` (auth specs) and `authenticated` (documents specs).

## Backend Architecture

### Request lifecycle

1. Cookie auth: `get_current_user()` in `app/dependencies.py` validates the `kg_session` cookie via `Session` table.
2. DB session: `get_db()` yields an `AsyncSession` per request.
3. ARQ pool: `get_arq_pool()` reads `app.state.arq_pool` (set at startup via lifespan in `main.py`).

### Document upload flow (transactional outbox pattern)

`POST /documents` in `app/routers/documents.py`:
1. Validate file type (allowed: pdf, txt, docx, md).
2. Upload bytes to MinIO.
3. Insert `Document`, `DocumentVersion` (status=PROCESSING), `ProcessingJob` (status=QUEUED) — all in one DB transaction.
4. Best-effort enqueue to Redis via arq with deterministic `_job_id = f"process_document:{version.id}"`.
5. If enqueue succeeds → set job status to DISPATCHED and commit.
6. If Redis is down → job stays QUEUED; background poller retries it.

**Poller** (`app/poller.py`): runs as an `asyncio.Task` in the lifespan. Every 30 s it:
1. Calls `reap_stale_processing_jobs()` (`app/reaper.py`) — resets PROCESSING jobs stuck for 10+ min (worker hard crash) back to QUEUED; marks FAILED and deletes MinIO object if attempts exhausted.
2. Queries QUEUED jobs and enqueues them with the same deterministic `_job_id`, preventing double-enqueue via ARQ's built-in deduplication.

### Data model (key relationships)

```
User
 └── Document (owner_id)
      └── DocumentVersion (version_number, status: PROCESSING|ACTIVE|SUPERSEDED|DELETED|REVIEW_REQUIRED)
           ├── DocumentChunk (content + Vector(1536) embedding)
           └── ProcessingJob (status: QUEUED|DISPATCHED|PROCESSING|COMPLETE|FAILED)
```

Only one `DocumentVersion` per document may have status=ACTIVE (partial unique index).

### Worker

`app/workers/main.py` — arq `WorkerSettings`. `process_document` pipeline:
1. Mark `ProcessingJob` PROCESSING, load `DocumentVersion`.
2. Download raw bytes from MinIO (`run_in_executor` — sync client).
3. Detect content type → extract text (`app/services/extractor.py`).
4. Chunk text (`app/services/chunker.py`).
5. Generate OpenAI embeddings (`app/services/embedder.py`).
6. `persist_results` (`app/workers/persistence.py`) — insert `DocumentChunk` rows, update search vector, supersede old ACTIVE version, activate new version, emit `INDEX_UPDATED` audit event — all in one transaction.

On error: `app/utils/worker_errors.py` classifies retryable vs non-retryable. Non-retryable (`ValueError`, `openai.AuthenticationError`, `openai.BadRequestError`) → immediate FAILED. Retryable → `raise Retry(defer=N)` up to `MAX_TRIES`. Permanent failure calls `persist_failure` (`app/workers/failure.py`) which also deletes the MinIO object.

Shared retry constant: `app/workers/constants.py` (`MAX_TRIES`, `RETRY_DELAYS`) — used by both worker and reaper.

Run worker: `uv run arq app.workers.main.WorkerSettings` (or via Docker: `worker` service in docker-compose).

## Frontend Architecture

Next.js 14 App Router. All pages under `src/app/`. API calls go through `src/lib/api/client.ts` using `credentials: "include"` for session cookie passthrough. Types in `src/types/index.ts` mirror the backend data model.

Post-login redirect lands on `/documents`. `/login` and `/register` use the shared `AuthForm` component. Middleware in `src/proxy.ts` handles auth redirects.

UI components are shadcn/ui (in `src/components/ui/`).

## Test Patterns

### Backend integration tests

Tests live in `backend/tests/` mirroring the app structure (`routers/`, `workers/`, `services/`).

- Shared fixtures in `tests/fixtures/` (`db.py`, `auth.py`, `arq.py`), loaded via `pytest_plugins` in `tests/conftest.py`
- `override_db` is autouse — patches `get_db` for every test
- `_arq_app_state` is autouse — sets `app.state.arq_pool` (lifespan doesn't run in ASGI tests)
- `mock_pool` overrides the `get_arq_pool` dependency; use when a test needs to assert on `enqueue_job` calls
- Engine created with `NullPool` — required so asyncpg binds to the per-test event loop
- Worker tests (`tests/workers/`) have their own `conftest.py` that patches `AsyncSessionLocal` in `workers/main.py`, `workers/persistence.py`, and `workers/failure.py` with a NullPool factory to avoid connection-reuse errors across test event loops

### Frontend unit tests

Jest with jsdom. Config in `frontend/jest.config.js`. Module alias `@/` maps to `src/`.
