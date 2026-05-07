"""Structured audit logging for user actions.

Emits JSON audit events that flow through the same logging pipeline
(stdout -> Fluent Bit -> Elasticsearch). All events are tagged with
event_type="audit" so they can be filtered in Kibana.

portal_id, user_id, and user_type are automatically included from
structlog contextvars (set by AuthMiddleware).

Usage:
    from verve_vero_common.logging.audit import audit

    # In an endpoint or service:
    audit.log("user.created", resource_type="chat_user", resource_id=user.id,
              detail="Chat user created via portal admin")

    audit.log("kb.document.uploaded", resource_type="document", resource_id=doc.id,
              detail=f"Uploaded {filename} to knowledge base {kb_id}")
"""

from typing import Any

import structlog

_audit_logger = structlog.get_logger("audit")


class AuditLogger:
    """Emit structured audit events for user actions."""

    def log(
        self,
        action: str,
        *,
        resource_type: str = "",
        resource_id: str = "",
        detail: str = "",
        **extra: Any,
    ):
        """Log an audit event.

        Args:
            action: What happened (e.g. "user.created", "agent.updated", "kb.deleted").
            resource_type: Type of resource acted on (e.g. "chat_user", "agent", "document").
            resource_id: ID of the resource.
            detail: Human-readable description.
            **extra: Additional context fields.
        """
        _audit_logger.info(
            action,
            event_type="audit",
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else "",
            detail=detail,
            **extra,
        )


audit = AuditLogger()
