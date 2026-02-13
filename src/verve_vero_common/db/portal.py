"""
Portal Context Management

Provides request-scoped portal identification using Python contextvars.
Designed for API Gateway + Lambda Authorizer architecture.

Usage:
------
    from verve_vero_common.db import set_current_portal

    @app.middleware("http")
    async def portal_middleware(request: Request, call_next):
        portal_id = request.headers.get("X-Portal-ID")
        set_current_portal(portal_id)
        try:
            response = await call_next(request)
        finally:
            set_current_portal(None)
        return response

    # For background jobs
    from verve_vero_common.db import PortalContext

    with PortalContext("portal_acme"):
        process_job()
"""

from contextvars import ContextVar
from typing import Optional

# Context variable to store current portal ID per request/task
_current_portal: ContextVar[Optional[str]] = ContextVar("current_portal", default=None)


def get_current_portal() -> Optional[str]:
    """
    Get the current portal ID from context.

    Returns:
        The portal ID set by middleware, or None if not set
    """
    return _current_portal.get()


def set_current_portal(portal_id: Optional[str]) -> None:
    """
    Set the current portal ID in context.

    Call this from middleware after extracting portal from:
    - Lambda Authorizer context (X-Portal-ID header)
    - JWT token claims (portal_id claim)
    - Request host/subdomain

    Args:
        portal_id: The portal identifier, or None to clear
    """
    _current_portal.set(portal_id)


class PortalContext:
    """
    Context manager for temporarily setting portal context.

    Useful for background jobs, scripts, or any code that needs
    to operate in the context of a specific portal without middleware.

    The previous portal context is restored on exit.

    Usage:
        with PortalContext("portal_acme"):
            # get_current_portal() returns "portal_acme"
            # database operations use portal_acme's database
            do_work()
        # original context restored
    """

    def __init__(self, portal_id: Optional[str]):
        self.portal_id = portal_id
        self.previous_portal: Optional[str] = None

    def __enter__(self) -> "PortalContext":
        self.previous_portal = get_current_portal()
        set_current_portal(self.portal_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        set_current_portal(self.previous_portal)
        return False
