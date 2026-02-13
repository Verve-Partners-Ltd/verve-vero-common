"""User type enumeration for role-based access control."""

from enum import Enum as PyEnum


class UserType(str, PyEnum):
    """User type enumeration"""

    SYSTEM_ADMIN = "system_admin"
    PORTAL_ADMIN = "portal_admin"
    CLIENT_ADMIN = "client_admin"
    CHAT_USER = "chat_user"
