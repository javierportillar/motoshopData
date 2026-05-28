"""Logging estructurado con structlog + PII redaction."""

from __future__ import annotations

import logging
import uuid

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

# Keys que deben ser redactadas en logs
PII_KEYS = frozenset({
    "password", "hashed_password", "token", "authorization",
    "nitter", "email", "telefono", "jwt_secret",
})


def redact_pii(logger, method_name, event_dict):
    """Processor que redacta valores de keys sensibles."""
    for key in list(event_dict.keys()):
        if key.lower() in PII_KEYS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def setup_logging():
    """Configura structlog con JSON output y PII redaction."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            redact_pii,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware que genera un request_id UUID por cada request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
