"""
Reusable Database Module for Multi-Database Portal Architecture

This module provides database session management for:
1. Public/Control Plane database - shared across all portals
2. Portal databases - one database per portal (complete isolation)

Usage:
------
# On startup:
from verve_vero_common.db import init_public_db, init_portal_db

init_public_db(settings.DATABASE_URL)
init_portal_db(settings.get_portal_database_url)

# In routes:
from verve_vero_common.db import get_public_db, get_portal_db

db: Session = Depends(get_public_db)
db: Session = Depends(get_portal_db)

Configuration:
--------------
Add DatabaseConfigMixin to your Settings class:

    from verve_vero_common.db import DatabaseConfigMixin

    class Settings(DatabaseConfigMixin, BaseSettings):
        ...
"""

from verve_vero_common.db.base import Base
from verve_vero_common.db.config import DatabaseConfigMixin
from verve_vero_common.db.portal import (
    get_current_portal,
    set_current_portal,
    PortalContext,
)
from verve_vero_common.db.public import (
    get_public_db,
    get_public_engine,
    init_public_db,
    PublicSession,
)
from verve_vero_common.db.session import (
    init_portal_db,
    get_portal_db,
    get_db_for_portal,
    get_engine_for_portal,
    clear_engine_cache,
    PortalSession,
)

__all__ = [
    # Base
    "Base",
    # Config mixin
    "DatabaseConfigMixin",
    # Portal context
    "get_current_portal",
    "set_current_portal",
    "PortalContext",
    # Public DB (control plane)
    "init_public_db",
    "get_public_db",
    "get_public_engine",
    "PublicSession",
    # Portal DB (per-portal)
    "init_portal_db",
    "get_portal_db",
    "get_db_for_portal",
    "get_engine_for_portal",
    "clear_engine_cache",
    "PortalSession",
]
