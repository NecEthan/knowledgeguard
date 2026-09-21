# Engineering Decisions

## Auth

A server-side session was chosen because it provides immediate server-side control over authentication and permissions. Each request validates the session against the database, so permission changes take effect on the user's next request without requiring additional session-invalidation logic. This does add an extra database lookup per authenticated request, but the lookup is lightweight and is not expected to noticeably slow down the application. If it becomes a bottleneck at scale, session lookups can be optimised or cached.

## Upload Doc

I chose a polling publisher because it provides the reliability I need while keeping the architecture simple. The dispatcher checks the PostgreSQL ProcessingJob table for queued jobs and publishes them to Redis, so a crash or Redis outage does not lose a committed job. CDC would provide lower latency and avoid repeated database polling, but it requires database specific transaction log infrastructure and is more complex to operate. Since document processing itself takes considerably longer than a few seconds, the small polling delay is an acceptable tradeoff for a simpler system.
