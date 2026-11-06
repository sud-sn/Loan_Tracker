"""App settings (Owner only) and the job / backup status shown in Settings (PRD section 13)."""

from __future__ import annotations

import json
from datetime import date, time
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.core.errors import AppError
from app.deps import Ctx
from app.engine import from_paise, to_paise
from app.models import BusinessSettings, JobRun
from app.services import audit

EDITABLE = (
    "licence_no", "lender_name", "lender_address", "max_rate_monthly", "due_soon_days", "due_window_days",
    "long_unpaid_days", "default_language", "balance_start_date", "opening_balance", "penalty_default_mode",
    "penalty_default_value", "penalty_grace_days", "staff_enabled", "staff_can_create_loans", "daily_summary_time",
    "retention_years", "max_upload_mb", "max_files_per_owner", "ltv_max_vehicle", "ltv_max_land",
    "emi_rounding_default", "broken_period_default", "advance_installments_default", "processing_fee_percent",
    "document_charges_default",
)
MONEY = ("opening_balance", "document_charges_default")  # stored in paise
TWO_DECIMALS = ("ltv_max_vehicle", "ltv_max_land", "emi_rounding_default", "processing_fee_percent")


def serialize(b: BusinessSettings) -> dict[str, Any]:
    out = {name: getattr(b, name) for name in EDITABLE}
    for name in MONEY:
        out[name] = from_paise(getattr(b, name))
    out["version"] = b.version
    return out


def _plain(value: Any) -> Any:
    if isinstance(value, (Decimal, date, time)):
        return str(value)
    return value


def update(ctx: Ctx, data: dict[str, Any]) -> BusinessSettings:
    b = ctx.business
    if data.get("version") != b.version:
        raise AppError("EDIT_CONFLICT", 409)
    changes: dict[str, Any] = {}
    for name in EDITABLE:
        if name not in data:
            continue
        value = data[name]
        if name in MONEY:
            value = to_paise(Decimal(value or 0))
        elif name in TWO_DECIMALS and value is not None:
            value = Decimal(value).quantize(Decimal("0.01"))
        if value != getattr(b, name):
            changes[name] = [_plain(getattr(b, name)), _plain(value)]
            setattr(b, name, value)
    audit.from_ctx(ctx, "settings.updated", "business", b.id, changes)
    ctx.db.commit()
    return b


def status(ctx: Ctx) -> dict[str, Any]:
    jobs = []
    for name in ("nightly", "daily_summary"):
        run = ctx.db.scalars(select(JobRun).where(JobRun.name == name).order_by(JobRun.created_at.desc()).limit(1)).first()
        jobs.append({
            "name": name, "status": run.status if run else "never", "run_date": run.run_date if run else None,
            "finished_at": run.finished_at if run else None, "detail": run.detail if run else {},
        })
    backup: dict[str, Any] = {"status": "unknown"}
    path = get_settings().backup_status_file
    try:
        backup = json.loads(path.read_text())
    except (OSError, ValueError):
        backup = {"status": "missing", "detail": "no backup status file found"}
    return {"jobs": jobs, "backup": backup}
