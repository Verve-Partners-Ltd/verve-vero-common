"""
Database Configuration Mixin

Add this mixin to your service's Settings class to enable database configuration.

Usage:
------
    from pydantic_settings import BaseSettings
    from verve_vero_common.db import DatabaseConfigMixin

    class Settings(DatabaseConfigMixin, BaseSettings):
        # Your other settings...
        pass

Environment Variables:
----------------------
Control Plane DB (public):
    DATABASE_URL: Full connection URL for control plane database
                  Example: postgresql://user:pass@host:5432/control_plane

Portal DBs (choose one approach):
    Option 1 - Template:
        PORTAL_DATABASE_URL_TEMPLATE: URL with {portal_id} placeholder
        Example: postgresql://user:pass@host:5432/{portal_id}

    Option 2 - Explicit mapping (JSON):
        PORTAL_DATABASE_URLS: JSON object mapping portal_id to URL
        Example: {"portal_acme": "postgresql://...", "portal_xyz": "postgresql://..."}

    Option 3 - Component-based (fallback):
        DB_HOST: Database host (default: localhost)
        DB_PORT: Database port (default: 5432)
        DB_USER: Database user (default: postgres)
        DB_PASSWORD: Database password
"""

import json
from typing import Optional


class DatabaseConfigMixin:
    """
    Mixin class providing database configuration for multi-database architecture.

    Supports:
    - Single control plane database (DATABASE_URL) - shared across all portals
    - Per-portal databases (template or explicit mapping)
    """

    # Control plane database (public)
    DATABASE_URL: Optional[str] = None

    # Portal database configuration
    PORTAL_DATABASE_URL_TEMPLATE: Optional[str] = None
    PORTAL_DATABASE_URLS: Optional[str] = None  # JSON string

    # Default connection components (used when template not provided)
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""

    def get_portal_database_url(self, portal_id: str) -> Optional[str]:
        """
        Get the database URL for a specific portal.

        Resolution order:
        1. Explicit mapping in PORTAL_DATABASE_URLS (JSON)
        2. Template-based URL using PORTAL_DATABASE_URL_TEMPLATE
        3. Default template using DB_* settings

        Args:
            portal_id: The portal identifier

        Returns:
            Database URL for the portal, or None if not configured
        """
        # 1. Check explicit mapping first
        if self.PORTAL_DATABASE_URLS:
            try:
                urls = json.loads(self.PORTAL_DATABASE_URLS)
                if portal_id in urls:
                    return urls[portal_id]
            except json.JSONDecodeError:
                pass

        # 2. Use template if provided
        if self.PORTAL_DATABASE_URL_TEMPLATE:
            return self.PORTAL_DATABASE_URL_TEMPLATE.format(portal_id=portal_id)

        # 3. Fall back to default template with DB_* settings
        if self.DB_HOST and self.DB_USER:
            password_part = f":{self.DB_PASSWORD}" if self.DB_PASSWORD else ""
            return (
                f"postgresql://{self.DB_USER}{password_part}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{portal_id}"
            )

        return None

    def has_public_db(self) -> bool:
        """Check if public/control plane database is configured."""
        return bool(self.DATABASE_URL)

    def has_portal_db_config(self) -> bool:
        """Check if portal database configuration is available."""
        return bool(
            self.PORTAL_DATABASE_URL_TEMPLATE
            or self.PORTAL_DATABASE_URLS
            or (self.DB_HOST and self.DB_USER)
        )
