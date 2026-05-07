"""Authentication and request logging middleware."""

import json
import logging
import time
import uuid
from typing import Callable, Optional

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from jose import jwt, ExpiredSignatureError, JWTError
from starlette.middleware.base import BaseHTTPMiddleware

from verve_vero_common.auth.context import set_auth_context, clear_auth_context

log = structlog.get_logger()

# ── Uvicorn access log health check filter ──────────────────────────

HEALTH_LOG_KEYWORDS = ("/healthz", "/readyz", "/health", "/liveness", "/readiness", "GET / HTTP")


class UvicornHealthCheckFilter(logging.Filter):
    """Suppress uvicorn access log lines for health/readiness probes."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(kw in msg for kw in HEALTH_LOG_KEYWORDS)

# Standardized header names (set by AWS API Gateway Lambda Authorizer)
USER_ID_HEADER = "X-User-ID"
USER_TYPE_HEADER = "X-User-Type"
PORTAL_ID_HEADER = "X-Portal-ID"
PORTAL_UUID_HEADER = "X-Portal-UUID"
TENANT_ID_HEADER = "X-Tenant-ID"
GATEWAY_SECRET_HEADER = "X-Gateway-Secret"

# Paths that skip token validation in dev mode (no auth required)
DEV_PUBLIC_PATHS = [
    "/user-service/api/v1/auth/login/portal",
    "/user-service/api/v1/auth/login/admin",
    "/user-service/api/v1/auth/login/chat",
    "/user-service/api/v1/auth/refresh",
    "/user-service/api/v1/health",
    "/user-service/api/v1/auth/sso/",
    "/portal-service/api/v1/portals/public/branding",
    "/cms-service/api/v1/site/public/branding",
    "/portal-service/api/v1/portals/internal/",
    "/portal-service/api/v1/agents/",
    "/portal-service/api/v1/internal/",
    "/user-service/api/v1/auth/forgot-password",
    "/user-service/api/v1/auth/verify-reset-token",
    "/user-service/api/v1/auth/reset-password",
    "/user-service/api/v1/auth/password-policy",
    "/user-service/api/v1/auth/mfa/setup-required",
    "/user-service/api/v1/auth/mfa/validate",
    "/user-service/api/v1/auth/mfa/setup-required/init",
    "/user-service/api/v1/auth/mfa/setup-required/confirm",
    "/user-service/api/v1/auth/system-sso/",
    "/docs",
    "/redoc",
    "/openapi.json",
]


class AuthMiddleware(BaseHTTPMiddleware):
    """Extract authentication context from request.

    Two modes controlled by dev_mode flag:
    - Production (dev_mode=False): reads X-User-ID, X-User-Type, X-Portal-ID
      headers set by API Gateway Lambda Authorizer. Validates X-Gateway-Secret.
    - Development (dev_mode=True): decodes JWT from Authorization Bearer token
      directly, so the frontend can authenticate without API Gateway.

    Args:
        app: The ASGI application
        gateway_secret: Shared secret for validating requests came through API Gateway.
        set_portal_context: Optional callback to set portal/tenant context for DB routing.
        dev_mode: When True, decode JWT from Bearer token instead of reading headers.
        jwt_public_key: PEM-encoded RSA public key for JWT verification (required in dev_mode).
        jwt_algorithm: JWT signing algorithm (default: RS256).
    """

    def __init__(
        self,
        app,
        gateway_secret: str = "",
        set_portal_context: Optional[Callable[[Optional[str]], None]] = None,
        dev_mode: bool = False,
        jwt_public_key: str = "",
        jwt_algorithm: str = "RS256",
    ):
        super().__init__(app)
        self.gateway_secret = gateway_secret
        self.set_portal_context = set_portal_context or (lambda x: None)
        self.dev_mode = dev_mode
        self.jwt_public_key = jwt_public_key
        self.jwt_algorithm = jwt_algorithm

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        user_id = None
        user_type = None
        portal_id = None
        portal_uuid = None

        if self.dev_mode:
            # Skip token check for public paths in dev mode
            path = request.url.path
            is_public = any(path.startswith(p) for p in DEV_PUBLIC_PATHS)

            # Dev mode: decode JWT from Authorization Bearer token
            auth_header = request.headers.get("Authorization", "")
            if not auth_header or not auth_header.startswith("Bearer "):
                if not is_public:
                    log.warning("missing_auth_token", path=path)
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Missing authentication token", "code": "missing_token"},
                    )
            else:
                try:
                    payload = jwt.decode(
                        auth_header[7:],
                        self.jwt_public_key,
                        algorithms=[self.jwt_algorithm],
                    )
                    if payload.get("type") == "access":
                        user_id = payload.get("sub")
                        user_type = payload.get("user_type")
                        portal_id = payload.get("portal_slug")
                        portal_uuid=payload.get("portal_id")
                except ExpiredSignatureError:
                    log.warning("expired_jwt_token", path=path)
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Token has expired", "code": "expired_token"},
                    )
                except JWTError:
                    log.warning("invalid_jwt_token", path=path)
        else:
            # Production: verify gateway secret and read headers
            gateway_secret = request.headers.get(GATEWAY_SECRET_HEADER)
            trusted = not self.gateway_secret or gateway_secret == self.gateway_secret

            if not trusted:
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
            portal_uuid = request.headers.get(PORTAL_UUID_HEADER)

        tenant_id = request.headers.get(TENANT_ID_HEADER)

        # Set portal/tenant context for database routing
        effective_portal = tenant_id or portal_id
        if effective_portal:
            self.set_portal_context(effective_portal)

        # Set auth context for role-based access control
        if user_id and user_type:
            set_auth_context(user_id=user_id, user_type=user_type, portal_id=portal_id, portal_uuid=portal_uuid)
            structlog.contextvars.bind_contextvars(
                user_id=user_id, user_type=user_type, portal_id=portal_id
            )

        try:
            response = await call_next(request)
            return response
        finally:
            clear_auth_context()
            self.set_portal_context(None)


LOG_SKIP_SUFFIXES = ("/healthz", "/readyz", "/health", "/liveness", "/readiness")

# Path segments to skip when extracting resource type/id
_PATH_SKIP_SEGMENTS = frozenset({
    "api", "v1", "v2", "v3", "portal", "internal", "public", "auth", "site",
})

# UUID pattern: 8-4-4-4-12 hex chars
_UUID_CHARS = frozenset("0123456789abcdef-")

_AUDIT_ACTION_MAP = {
    "POST": "created",
    "PUT": "updated",
    "PATCH": "updated",
    "DELETE": "deleted",
}


def _is_health_check(path: str) -> bool:
    """Return True for health/readiness probe paths that should not be logged."""
    return path == "/" or path.endswith(LOG_SKIP_SUFFIXES)


def _looks_like_id(segment: str) -> bool:
    """Return True if segment looks like a UUID or numeric ID."""
    if segment.isdigit():
        return True
    # UUID check: correct length and only hex + dashes
    if len(segment) == 36 and set(segment.lower()) <= _UUID_CHARS:
        return True
    return False


def _extract_resource_info(path: str) -> tuple[str, str]:
    """Extract resource type and ID from a URL path.

    Examples:
        /user-service/api/v1/portal/chat-users           → ("chat-users", "")
        /user-service/api/v1/portal/chat-users/abc-123    → ("chat-users", "abc-123")
        /api/v1/agents/abc-123/db-tables                  → ("db-tables", "")
        /api/v1/agents/abc-123/db-tables/def-456          → ("db-tables", "def-456")
    """
    segments = [s for s in path.strip("/").split("/") if s]

    # Filter out known prefixes and IDs to find resource segments
    resource_type = ""
    resource_id = ""

    for segment in segments:
        lower = segment.lower()
        if lower in _PATH_SKIP_SEGMENTS or lower.endswith("-service"):
            continue
        if _looks_like_id(segment):
            resource_id = segment
        else:
            # New resource name found — reset resource_id (it belonged to parent)
            resource_type = segment
            resource_id = ""

    return resource_type, resource_id


async def _extract_id_from_response(response: Response) -> tuple[str, Response]:
    """Read response body to extract 'id' field, then rebuild the response.

    Only called for POST 201 (single-object create) — body is always small.
    Returns the extracted ID and a new Response with the same body.
    """
    body = b""
    async for chunk in response.body_iterator:
        body += chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")

    resource_id = ""
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            resource_id = str(data.get("id") or data.get("uuid") or "")
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    new_response = Response(
        content=body,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
    )
    return resource_id, new_response


class RequestIdLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID tracking, request logging, and audit trail.

    Ensures every request has a unique ID for tracing across services.
    Logs request method, path, status code, and duration.
    Automatically emits audit events for mutating requests (POST/PUT/PATCH/DELETE).
    Propagates x-request-id in response header.
    Skips logging for health check / readiness probe paths.
    """

    def __init__(self, app, service_name: str = "unknown"):
        super().__init__(app)
        self.service_name = service_name

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            service_name=self.service_name,
        )

        start_time = time.time()
        response = await call_next(request)
        duration_ms = int((time.time() - start_time) * 1000)

        path = str(request.url.path)
        # Skip logging for health checks and probes
        if not _is_health_check(path):
            log.info(
                "http_request",
                method=request.method,
                path=path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )

            # Audit trail for mutating requests
            if request.method in _AUDIT_ACTION_MAP:
                resource_type, resource_id = _extract_resource_info(path)

                # For POST 201 (create), read response body to get resource ID
                # Single-object creates are small (~1KB), safe to buffer
                if not resource_id and request.method == "POST" and response.status_code == 201:
                    resource_id, response = await _extract_id_from_response(response)

                if 200 <= response.status_code < 300:
                    result = "success"
                elif 400 <= response.status_code < 500:
                    result = "failed"
                else:
                    result = "error"

                action = _AUDIT_ACTION_MAP[request.method]
                log.info(
                    f"{resource_type}.{action}" if resource_type else action,
                    event_type="audit",
                    result=result,
                    method=request.method,
                    path=path,
                    status_code=response.status_code,
                    resource_type=resource_type,
                    resource_id=resource_id,
                )

        response.headers["x-request-id"] = request_id
        return response
