"""Append-only audit log (PRD section 12). Sensitive values are redacted before saving."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog

SENSITIVE = ("aadhaar", "password", "totp", "secret", "token", "otp")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("[redacted]" if any(s in k.lower() for s in SENSITIVE) and "last4" not in k.lower() else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def record(
    db: Session,
    action: str,
    *,
    user_id: uuid.UUID | None,
    entity_type: str | None = None,
    entity_id: object | None = None,
    changes: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id, action=action, entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            changes=redact(changes or {}), ip=ip, user_agent=user_agent, request_id=request_id,
        )
    )


def from_ctx(ctx: Any, action: str, entity_type: str | None = None, entity_id: object | None = None,
             changes: dict[str, Any] | None = None) -> None:
    record(
        ctx.db, action, user_id=ctx.user.id, entity_type=entity_type, entity_id=entity_id, changes=changes,
        ip=ctx.ip, user_agent=ctx.user_agent, request_id=ctx.request_id,
    )
