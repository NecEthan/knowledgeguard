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


