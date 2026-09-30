"""Request logging middleware.

Emits one structured log entry per HTTP request containing:
    request_id  — UUID generated per request for log correlation
    service     — "backend"
    method      — HTTP method
    path        — request path
    status_code — response status code
    duration_ms — total handler latency in milliseconds

user_id is bound separately by get_current_user() (app/dependencies.py) once
the session cookie has been resolved, so it appears in all subsequent log
entries within the same request.
"""

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        start = time.monotonic()

        # Clear any previous request context and bind fresh values.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            service="backend",
        )

        response = await call_next(request)

        duration_ms = round((time.monotonic() - start) * 1000, 1)
        logger.info(
            "request_log",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        return response
