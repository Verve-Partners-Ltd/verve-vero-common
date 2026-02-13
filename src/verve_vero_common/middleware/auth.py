"""Authentication and request logging middleware."""

import time
import uuid
from typing import Callable, Optional

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from verve_vero_common.auth.context import set_auth_context, clear_auth_context

log = structlog.get_logger()

# Standardized header names (set by AWS API Gateway Lambda Authorizer)
USER_ID_HEADER = "X-User-ID"
USER_TYPE_HEADER = "X-User-Type"
PORTAL_ID_HEADER = "X-Portal-ID"
TENANT_ID_HEADER = "X-Tenant-ID"
GATEWAY_SECRET_HEADER = "X-Gateway-Secret"


class AuthMiddleware(BaseHTTPMiddleware):
    """Extract authentication and portal context from API Gateway headers.

    Verifies X-Gateway-Secret to prevent header spoofing from direct access.
    Only trusts auth headers (X-User-ID, X-User-Type, etc.) when the
    gateway secret matches, ensuring requests came through API Gateway.

    Args:
        app: The ASGI application
        gateway_secret: Shared secret for validating requests came through API Gateway.
            If empty, all requests are trusted (for local development).
        set_portal_context: Optional callback to set portal/tenant context for DB routing.
            Signature: (portal_id: Optional[str]) -> None
    """

    def __init__(
        self,
        app,
        gateway_secret: str = "",
        set_portal_context: Optional[Callable[[Optional[str]], None]] = None,
    ):
        super().__init__(app)
        self.gateway_secret = gateway_secret
        self.set_portal_context = set_portal_context or (lambda x: None)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Verify request came through API Gateway by checking the shared secret
        gateway_secret = request.headers.get(GATEWAY_SECRET_HEADER)
        trusted = not self.gateway_secret or gateway_secret == self.gateway_secret

        if not trusted:
            # Request didn't come through gateway - ignore all auth headers
            log.warning(
                "untrusted_request",
                path=request.url.path,
                reason="missing_or_invalid_gateway_secret",
            )
            try:
                response = await call_next(request)
                return response
            finally:
                clear_auth_context()

        user_id = request.headers.get(USER_ID_HEADER)
        user_type = request.headers.get(USER_TYPE_HEADER)
        portal_id = request.headers.get(PORTAL_ID_HEADER)
        tenant_id = request.headers.get(TENANT_ID_HEADER)

        # Set portal/tenant context for database routing
        effective_portal = tenant_id or portal_id
        if effective_portal:
            self.set_portal_context(effective_portal)

        # Set auth context for role-based access control
        if user_id and user_type:
            set_auth_context(user_id=user_id, user_type=user_type, portal_id=portal_id)
            structlog.contextvars.bind_contextvars(
                user_id=user_id, user_type=user_type, portal_id=portal_id
            )

        try:
            response = await call_next(request)
            return response
        finally:
            clear_auth_context()
            self.set_portal_context(None)


class RequestIdLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID tracking and request logging.

    Ensures every request has a unique ID for tracing across services.
    Logs request method, path, status code, and duration.
    Propagates x-request-id in response header.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start_time = time.time()
        response = await call_next(request)
        duration_ms = int((time.time() - start_time) * 1000)

        log.info(
            "http_request",
            method=request.method,
            path=str(request.url.path),
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        response.headers["x-request-id"] = request_id
        return response
