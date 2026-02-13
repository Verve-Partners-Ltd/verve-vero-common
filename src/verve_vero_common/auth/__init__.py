"""Authentication and authorization module."""

from verve_vero_common.auth.types import UserType
from verve_vero_common.auth.context import (
    AuthContext,
    set_auth_context,
    get_auth_context,
    clear_auth_context,
)
from verve_vero_common.auth.dependencies import (
    require_auth,
    get_current_user,
    require_system_admin,
    require_portal_admin,
    require_client_admin,
)

__all__ = [
    "UserType",
    "AuthContext",
    "set_auth_context",
    "get_auth_context",
    "clear_auth_context",
    "require_auth",
    "get_current_user",
    "require_system_admin",
    "require_portal_admin",
    "require_client_admin",
]
