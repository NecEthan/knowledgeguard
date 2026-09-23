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
