"""Authentication and request logging middleware."""

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

# Standardized header names (set by AWS API Gateway Lambda Authorizer)
USER_ID_HEADER = "X-User-ID"
USER_TYPE_HEADER = "X-User-Type"
PORTAL_ID_HEADER = "X-Portal-ID"
PORTAL_UUID_HEADER = "X-Portal-UUID"
TENANT_ID_HEADER = "X-Tenant-ID"
PORTAL_UUID_HEADER = "X-Portal-UUID"
GATEWAY_SECRET_HEADER = "X-Gateway-Secret"

# Paths that skip token validation in dev mode (no auth required)
DEV_PUBLIC_PATHS = [
    "/api/v1/auth/login/portal",
    "/api/v1/auth/login/admin",
    "/api/v1/auth/login/chat",
    "/api/v1/auth/refresh",
    "/api/v1/health",
    "/api/v1/portals/public/branding",
    "/api/v1/portals/internal/",
    "/api/v1/agents/",
    "/api/v1/internal/",
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
