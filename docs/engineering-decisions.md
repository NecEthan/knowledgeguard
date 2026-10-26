# Engineering Decisions

## Auth

A server-side session was chosen because it provides immediate server-side control over authentication and permissions. Each request validates the session against the database, so permission changes take effect on the user's next request without requiring additional session-invalidation logic. This does add an extra database lookup per authenticated request, but the lookup is lightweight and is not expected to noticeably slow down the application. If it becomes a bottleneck at scale, session lookups can be optimised or cached.

## Upload Doc

Document, DocumentVersion, ProcessingJob all insert in one DB transaction before touching Redis. If Redis is down, the record still exists in DB with status QUEUED no work is lost. This adds poller complexity and will have to query the DB every now and then but this is a cheap process to do.

I chose a polling publisher because it provides the reliability I need while keeping the architecture simple. The dispatcher checks the PostgreSQL ProcessingJob table for queued jobs and publishes them to Redis, so a crash or Redis outage does not lose a committed job. CDC would provide lower latency and avoid repeated database polling, but it requires database specific transaction log infrastructure and is more complex to operate. Since document processing itself takes considerably longer than a few seconds, the small polling delay is an acceptable tradeoff for a simpler system.

If error occurs after job is enqueued, the job status will not be set to DISPATCHED resulting in a job being enqueued twice because the polling system will pick up jobs with status QUEUED, enqueue job function internally checks if a job with the same \_job_id already exists if does then returns None.

# Processing Doc

I added a retry to this pipeline because just cause it fails once does not mean it will fail on the next try if the error is a transient error. I have added list of some key non retryable errors so if we encounter them we do not retry which would waste worker capacity and resources.

Created a new thread for communicating with MinIO because its API calls are synchronous and could block the FastAPI event loop.

Added reaper to recover documents stuck mid-processing. If a worker crashes hard (SIGKILL, power loss), the job stays in PROCESSING forever.
The reaper runs every 30s and resets any PROCESSING job where updated_at hasn't changed for 10+ minutes back to QUEUED so the
poller re-dispatches it. Jobs that exceed max attempts are marked FAILED and their MinIO object is deleted.

# Multiple users update DOC Metadata at same time

I will update metadata using partial updates, changing only the fields the user modified rather than replacing the entire metadata object on every request. If we updated all fields on each request, a concurrent request containing stale values could overwrite newer data. With partial updates, stale unchanged fields are never written back, so concurrent changes to different fields are preserved. PostgreSQL coordinates concurrent updates to the same row.

Another option would be optimistic locking, but that would add additional complexity for what we want to acheive. Since we are only updating the fields that actually changed, optimistic locking is not necessary unless we need to detect and prevent concurrent updates to the same field. In this case, updating data does not rely on previous data so it is not strictly needed.

# Multiple users add Doc version at same time

We use the `"UniqueConstraint("document_id", "version_number", name="uq_document_version")` contraint so that we prevent duplicate document versions from being added. If DB commits first transaction then the second transaction will throw a constraint error which we handle and retry with an incremented verison number, if the retry fails after the number of attempts then we rollback and throw an error.

# Add duplicate file upload

We store a hashed value for file upload so we check if hashed value in db if so then throw error cannot upload duplicate file.
A unique database constraint on the hash provides an additional safeguard against two identical files being uploaded concurrently.

# LLM Rate Limiting

Single API key means all users share one OpenAI RPM/TPM quota. Three controls protect it:

**Query rate limit** — `POST /query` is capped at 20 requests/minute per IP via slowapi/Redis (same pattern as login). Each query costs 2 OpenAI calls (embed + chat). 20/min allows ~1 query every 3 seconds — fine for interactive use, stops scripted abuse. Limit is per-IP so each user gets an independent budget. Corporate NAT is the edge case — many users behind one IP share the budget. Fix if needed: switch key function in `app/limiter.py` to user ID. To handle more users, upgrade OpenAI tier or add a second API key to multiply quota.

**Worker concurrency cap** — ARQ limited to 5 concurrent jobs (`max_jobs=5`). One document can produce 100+ embedding batches; 10 simultaneous uploads without a cap would blast the embeddings RPM limit. The 6th job waits in Redis — no work lost. 5 jobs × 100 chunks ≈ 500 embedding calls/min, within tier 1 limits. Raise in `config.py` as tier increases.

**Worker 429 retry** — Generic transient retry delay is 10s, too short for OpenAI's 60s rate limit window. Explicit `openai.RateLimitError` branch defers retry by 60s. `MAX_TRIES` raised 3→4 to allow three retries (up to 3 min total) before permanent failure. Worker SDK `max_retries` also raised 2→4 — these are silent client-level retries before ARQ sees the error, safe to increase since worker jobs are not user-facing.

# Concurrency & Infrastructure Sizing

## Uvicorn Workers (HTTP)

The backend runs with `--workers 2`, meaning two separate Python processes each with their own asyncio event loop. A single worker handles I/O-bound work (DB queries, Redis, MinIO) efficiently via async, but bcrypt password hashing is CPU-bound and blocks the event loop while it runs. A second worker means bcrypt on one process does not delay unrelated requests on the other. Two workers were chosen rather than four because each worker holds its own DB connection pool, and the total connection count across all workers must stay within PostgreSQL's `max_connections` limit.

## ARQ Worker (Background Jobs)

The ARQ worker is a separate container that has no HTTP port and never responds to user requests. Its sole job is to pull document processing jobs off the Redis queue and execute the pipeline: download from MinIO, extract text, chunk, embed, persist vectors. This is kept separate from the HTTP workers because the pipeline is slow (seconds to minutes depending on document size) and must not block API responses. One ARQ worker is sufficient for the current load — document processing is not on the critical path for the user, and ARQ supports horizontal scaling (add more worker containers) if throughput needs to increase.

## Database Connection Pool

SQLAlchemy's default pool is `pool_size=5, max_overflow=10` giving 15 maximum connections per process. At 200 concurrent users all making authenticated requests, 15 connections causes severe queuing — requests wait up to 30 seconds for a connection to free up, resulting in timeouts and failures.

The pool is set to `pool_size=30, max_overflow=20` (50 max per worker). With 2 HTTP workers this means up to 100 connections to PostgreSQL. The ARQ worker and poller/reaper also hold connections, bringing the realistic peak to around 110–120. PostgreSQL `max_connections` is set to 200 to give headroom.

`pool_recycle=1800` closes and reopens connections older than 30 minutes to prevent stale connections after network interruptions. `pool_pre_ping=True` tests each borrowed connection before use and discards it if dead, preventing errors from being surfaced to users.

The right long-term solution at higher scale is PgBouncer — a connection pooler that sits in front of PostgreSQL and multiplexes thousands of application connections down to a small number of real database connections, since PostgreSQL is memory-intensive per connection (~5–10 MB RAM each).

