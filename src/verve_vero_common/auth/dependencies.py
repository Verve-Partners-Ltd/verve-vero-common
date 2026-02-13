"""FastAPI dependencies for role-based access control."""

from fastapi import HTTPException, status

from verve_vero_common.auth.context import AuthContext, get_auth_context
from verve_vero_common.auth.types import UserType


def require_auth() -> AuthContext:
    """Dependency to require authentication"""
    context = get_auth_context()
    if not context:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return context


def get_current_user() -> dict:
    """Get current user information from auth context"""
    context = require_auth()
    return {
        "user_id": context.user_id,
        "user_type": context.user_type.value,
        "portal_id": context.portal_id,
    }


def require_system_admin() -> dict:
    """Dependency to require System Admin role"""
    context = require_auth()
    if context.user_type != UserType.SYSTEM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System Admin access required"
        )
    return {
        "user_id": context.user_id,
        "user_type": context.user_type.value,
        "portal_id": context.portal_id,
    }


def require_portal_admin() -> dict:
    """Dependency to require Portal Admin role"""
    context = require_auth()
    if context.user_type != UserType.PORTAL_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Portal Admin access required"
        )
    if not context.portal_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Portal context required"
        )
    return {
        "user_id": context.user_id,
        "user_type": context.user_type.value,
        "portal_id": context.portal_id,
    }


def require_client_admin() -> dict:
    """Dependency to require Client Admin or Portal Admin role"""
    context = require_auth()
    if context.user_type not in [UserType.CLIENT_ADMIN, UserType.PORTAL_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client Admin or Portal Admin access required"
        )
    if not context.portal_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Portal context required"
        )
    return {
        "user_id": context.user_id,
        "user_type": context.user_type.value,
        "portal_id": context.portal_id,
    }
