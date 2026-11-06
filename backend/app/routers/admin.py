"""Owner-only: reports, settings, audit log, import, full export, push subscriptions, health."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, time
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text

from app.config import get_settings
from app.core import clock
from app.core.errors import AppError
from app.db import get_engine
from app.deps import DB, CtxDep, OwnerCtx, StepUpCtx
from app.engine import from_paise
from app.engine.schedule import ROUNDING_STEPS
from app.models import (
    AuditLog,
    Borrower,
    CashEntry,
    Category,
    Loan,
    Payment,
    PaymentAllocation,
    PushSubscription,
    ScheduleItem,
    User,
)
from app.schemas.common import Ok
from app.services import audit, importer, reports
from app.services import settings as settings_service

router = APIRouter(tags=["admin"])
health = APIRouter(tags=["health"])


class SettingsIn(BaseModel):
    version: int
    licence_no: str | None = Field(default=None, max_length=80)
    lender_name: str | None = Field(default=None, max_length=120)
    lender_address: str | None = Field(default=None, max_length=500)
    max_rate_monthly: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=4)
    due_soon_days: int | None = Field(default=None, ge=0, le=60)
    due_window_days: int | None = Field(default=None, ge=1, le=90)
    long_unpaid_days: int | None = Field(default=None, ge=1, le=3650)
    default_language: Literal["en", "ta"] | None = None
    balance_start_date: date | None = None
    opening_balance: Decimal | None = Field(default=None, decimal_places=2)
    penalty_default_mode: Literal["off", "per_day", "pct_month"] | None = None
    penalty_default_value: Decimal | None = Field(default=None, ge=0, decimal_places=4)
    penalty_grace_days: int | None = Field(default=None, ge=0, le=365)
    staff_enabled: bool | None = None
    staff_can_create_loans: bool | None = None
    daily_summary_time: time | None = None
    retention_years: int | None = Field(default=None, ge=1, le=50)
    max_upload_mb: int | None = Field(default=None, ge=1, le=50)
    max_files_per_owner: int | None = Field(default=None, ge=1, le=200)
    ltv_max_vehicle: Decimal | None = Field(default=None, gt=0, le=100, decimal_places=2)
    ltv_max_land: Decimal | None = Field(default=None, gt=0, le=100, decimal_places=2)
    emi_rounding_default: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    broken_period_default: Literal["none", "first_installment", "upfront"] | None = None
    advance_installments_default: int | None = Field(default=None, ge=0, le=12)
    processing_fee_percent: Decimal | None = Field(default=None, ge=0, le=25, decimal_places=2)
    document_charges_default: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    bounce_charge_default: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    foreclosure_charge_percent: Decimal | None = Field(default=None, ge=0, le=25, decimal_places=2)

    @field_validator("emi_rounding_default")
    @classmethod
    def _step(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value not in ROUNDING_STEPS:
            raise ValueError("rounding must be 0.01, 1, 5, 10, 50 or 100")
        return value


class PushIn(BaseModel):
    endpoint: str = Field(max_length=2000)
    keys: dict[str, str]


@router.get("/settings")
def get_settings_(ctx: CtxDep) -> dict[str, Any]:
    out = settings_service.serialize(ctx.business)
    if not ctx.is_owner:
        # Staff see what they need to work; staff who give loans also need the new-loan defaults.
        return {k: out[k] for k in ("due_soon_days", "due_window_days", "long_unpaid_days", "default_language",
                                    "lender_name", "ltv_max_vehicle", "ltv_max_land", "emi_rounding_default",
                                    "broken_period_default", "advance_installments_default",
                                    "processing_fee_percent", "document_charges_default", "max_rate_monthly",
                                    "bounce_charge_default", "foreclosure_charge_percent")}
    return out


@router.put("/settings")
def put_settings(data: SettingsIn, ctx: OwnerCtx) -> dict[str, Any]:
    changes = data.model_dump(exclude_unset=True)
    return settings_service.serialize(settings_service.update(ctx, changes))


@router.get("/settings/status")
def settings_status(ctx: OwnerCtx) -> dict[str, Any]:
    return settings_service.status(ctx)


@router.get("/audit")
def audit_log(ctx: OwnerCtx, page: int = Query(1, ge=1), page_size: int = Query(50, le=200),
              action: str | None = None, entity_id: str | None = None) -> dict[str, Any]:
    stmt = select(AuditLog, User.name).outerjoin(User, User.id == AuditLog.user_id)
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    rows = ctx.db.execute(stmt.order_by(AuditLog.at.desc()).limit(page_size).offset((page - 1) * page_size)).all()
    return {"items": [{"id": a.id, "at": a.at, "user": name, "action": a.action, "entity_type": a.entity_type,
                       "entity_id": a.entity_id, "changes": a.changes, "ip": str(a.ip) if a.ip else None}
                      for a, name in rows], "page": page, "page_size": page_size}


def _range(start: date | None, end: date | None) -> tuple[date, date]:
    end = end or clock.today()
    start = start or end.replace(day=1)
    if end < start:
        raise AppError("RANGE_INVALID", 422)
    return start, end


def _export(ctx: Any, kind: str, data: list[dict[str, Any]], fmt: str, lang: str | None, subtitle: str) -> Response:
    from app.deps import require_step_up  # noqa: F401 - documents that exports need step-up

    body, media = reports.export(kind, lang or ctx.lang, ctx.business, data, fmt=fmt, subtitle=subtitle)
    audit.from_ctx(ctx, f"export.report.{kind}", None, None, {"fmt": fmt})
    ctx.db.commit()
    return Response(body, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{kind}.{fmt}"'})


@router.get("/reports/collections")
def report_collections(ctx: OwnerCtx, start: date | None = None, end: date | None = None,
                       group: Literal["day", "month"] = "day") -> list[dict[str, Any]]:
    s, e = _range(start, end)
    return reports.collections(ctx.db, s, e, group)


@router.get("/reports/outstanding")
def report_outstanding(ctx: OwnerCtx) -> list[dict[str, Any]]:
    return reports.outstanding_by_borrower(ctx.db, clock.today())


@router.get("/reports/ageing")
def report_ageing(ctx: OwnerCtx) -> list[dict[str, Any]]:
    from app.services import dues

    ageing = dues.counts(ctx.db, ctx.business, clock.today())["ageing"]
    return [{"bucket": k, **v} for k, v in ageing.items()]


@router.get("/reports/interest")
def report_interest(ctx: OwnerCtx, start: date | None = None, end: date | None = None,
                    group: Literal["day", "month"] = "month") -> list[dict[str, Any]]:
    s, e = _range(start, end)
    return [{"period": r["period"], "interest": r["interest"], "penalty": r["penalty"]}
            for r in reports.collections(ctx.db, s, e, group)]


@router.get("/reports/{kind}/export")
def report_export(kind: Literal["collections", "outstanding", "ageing", "interest"], ctx: StepUpCtx,
                  fmt: Literal["csv", "pdf"] = "pdf", lang: Literal["en", "ta"] | None = None,
                  start: date | None = None, end: date | None = None,
                  group: Literal["day", "month"] = "day") -> Response:
    s, e = _range(start, end)
    subtitle = f"{s.strftime('%d/%m/%Y')} – {e.strftime('%d/%m/%Y')}"
    if kind == "collections" or kind == "interest":
        data = reports.collections(ctx.db, s, e, group)
    elif kind == "outstanding":
        data, subtitle = reports.outstanding_by_borrower(ctx.db, clock.today()), clock.today().strftime("%d/%m/%Y")
    else:
        data = report_ageing(ctx)
    return _export(ctx, kind, data, fmt, lang, subtitle)


@router.get("/import/template.xlsx")
def import_template(ctx: OwnerCtx) -> Response:
    return Response(importer.template(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="loan-tracker-import.xlsx"'})


@router.post("/import/preview")
async def import_preview(ctx: OwnerCtx, file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise AppError("FILE_TOO_LARGE", 413, max_mb=10)
    return importer.summary(importer.parse(data, file.filename or "import.xlsx"))


@router.post("/import/commit")
async def import_commit(ctx: OwnerCtx, file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read(10 * 1024 * 1024 + 1)
    return importer.commit(ctx, data, file.filename or "import.xlsx")


def _rows(db: Any, model: Any) -> list[dict[str, Any]]:
    out = []
    for row in db.scalars(select(model)):
        item = {}
        for col in model.__table__.columns:
            value = getattr(row, col.key, None)
            if col.key in ("aadhaar_encrypted", "aadhaar_hash", "password_hash", "totp_secret_encrypted"):
                continue
            item[col.key] = value.hex() if isinstance(value, bytes) else value
        out.append(item)
    return out


@router.get("/export/full.zip")
def full_export(ctx: StepUpCtx) -> Response:
    """Owner-triggered full data export (PRD section 13). Aadhaar is masked: only the last 4 digits."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, model in (("borrowers", Borrower), ("loans", Loan), ("schedule", ScheduleItem),
                            ("payments", Payment), ("allocations", PaymentAllocation), ("cash_entries", CashEntry),
                            ("categories", Category)):
            zf.writestr(f"{name}.json", json.dumps(_rows(ctx.db, model), default=str, ensure_ascii=False, indent=1))
        zf.writestr("README.txt", "Money columns are in paise (divide by 100 for rupees). Aadhaar numbers are not "
                                  "included; aadhaar_last4 is.\n")
    audit.from_ctx(ctx, "export.full", None, None, {})
    ctx.db.commit()
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="loan-tracker-{clock.today()}.zip"'})


@router.get("/push/vapid-public-key")
def vapid_key(ctx: CtxDep) -> dict[str, str | None]:
    return {"key": get_settings().vapid_public_key}


@router.post("/push/subscribe", response_model=Ok)
def push_subscribe(data: PushIn, ctx: OwnerCtx) -> Ok:
    existing = ctx.db.scalars(select(PushSubscription).where(PushSubscription.endpoint == data.endpoint)).first()
    if existing is None:
        ctx.db.add(PushSubscription(user_id=ctx.user.id, endpoint=data.endpoint, p256dh=data.keys.get("p256dh", ""),
                                    auth=data.keys.get("auth", "")))
        ctx.db.commit()
    return Ok()


@health.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@health.get("/readyz")
def readyz(db: DB) -> dict[str, Any]:
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        raise AppError("DATABASE_UNAVAILABLE", 503) from exc
    storage = get_settings().storage_dir
    return {"status": "ready", "database": "ok", "storage": "ok" if storage.exists() else "missing",
            "engine": get_engine().dialect.name, "zero": str(from_paise(0))}
