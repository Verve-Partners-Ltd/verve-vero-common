"""Authentication context management using contextvars."""

from contextvars import ContextVar
from typing import Optional

from verve_vero_common.auth.types import UserType


class AuthContext:
    """Authentication context for the current request.

    Contains only the essential fields needed for authorization:
    - user_id: identity
    - user_type: role-based access control
    - portal_id: tenant isolation
    """

    user_id: str
    user_type: UserType
    portal_id: Optional[str]


# Context variable to store auth context per request
_auth_context: ContextVar[Optional[AuthContext]] = ContextVar("auth_context", default=None)


def set_auth_context(
    user_id: str, user_type: str, portal_id: Optional[str]
) -> None:
    """Set authentication context for the current request"""
    context = AuthContext()
    context.user_id = user_id
    context.user_type = UserType(user_type)
    context.portal_id = portal_id if portal_id else None
    _auth_context.set(context)


def get_auth_context() -> Optional[AuthContext]:
    """Get current authentication context"""
    return _auth_context.get()


def clear_auth_context() -> None:
    """Clear authentication context"""
    _auth_context.set(None)
