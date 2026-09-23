"""Shared constants for the document processing worker."""

MAX_TRIES = 3
RETRY_DELAYS = [10, 60]  # seconds per attempt: attempt 1 waits 10s, attempt 2 waits 60s
