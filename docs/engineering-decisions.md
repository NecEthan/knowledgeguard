# Engineering Decisions

## Auth

A server-side session was chosen because it provides immediate server-side control over authentication and permissions. Each request validates the session against the database, so permission changes take effect on the user's next request without requiring additional session-invalidation logic. This does add an extra database lookup per authenticated request, but the lookup is lightweight and is not expected to noticeably slow down the application. If it becomes a bottleneck at scale, session lookups can be optimised or cached.
