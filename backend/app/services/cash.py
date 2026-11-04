"""Own spending and other income, typed in by hand (PRD section 7). Every change keeps history."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select

from app.core import clock
from app.core.errors import AppError
from app.core.text import nfc
from app.deps import Ctx
from app.engine import from_paise, to_paise
from app.models import CashEntry, CashEntryHistory, Category
from app.security.tokens import now
from app.services import audit


def _snapshot(e: CashEntry) -> dict[str, Any]:
    return {"entry_date": e.entry_date.isoformat(), "direction": e.direction, "category_id": str(e.category_id),
            "amount": str(from_paise(e.amount)), "mode": e.mode, "note": e.note,
            "deleted": e.deleted_at is not None}


def _history(ctx: Ctx, e: CashEntry, action: str) -> None:
    ctx.db.add(CashEntryHistory(cash_entry_id=e.id, action=action, entry_version=e.version, snapshot=_snapshot(e),
                                changed_by=ctx.user.id))


def _category(ctx: Ctx, category_id: uuid.UUID, direction: str) -> Category:
    cat = ctx.db.get(Category, category_id)
    if cat is None or not cat.is_active:
        raise AppError("CATEGORY_NOT_FOUND", 404)
    if (cat.kind == "expense") != (direction == "out"):
        raise AppError("CATEGORY_KIND_MISMATCH", 422)
    return cat


def create(ctx: Ctx, *, direction: str, category_id: uuid.UUID, amount: Any, entry_date: date | None, mode: str,
           note: str | None, idempotency_key: str | None) -> CashEntry:
    if idempotency_key:
        existing = ctx.db.scalars(select(CashEntry).where(CashEntry.idempotency_key == idempotency_key)).first()
        if existing:
            return existing
    on = entry_date or clock.today()
    if on > clock.today():
        raise AppError("DATE_IN_FUTURE", 422)
    _category(ctx, category_id, direction)
    e = CashEntry(entry_date=on, direction=direction, category_id=category_id, amount=to_paise(amount), mode=mode,
                  note=nfc(note), idempotency_key=idempotency_key, created_by=ctx.user.id)
    ctx.db.add(e)
    ctx.db.flush()
    _history(ctx, e, "create")
    audit.from_ctx(ctx, "cash_entry.created", "cash_entry", e.id, _snapshot(e))
    ctx.db.commit()
    return e


def update(ctx: Ctx, entry_id: uuid.UUID, version: int, changes: dict[str, Any]) -> CashEntry:
    e = ctx.db.get(CashEntry, entry_id)
    if e is None or e.deleted_at is not None:
        raise AppError("ENTRY_NOT_FOUND", 404)
    if e.version != version:
        raise AppError("EDIT_CONFLICT", 409)
    before = _snapshot(e)
    if "entry_date" in changes and changes["entry_date"]:
        if changes["entry_date"] > clock.today():
            raise AppError("DATE_IN_FUTURE", 422)
        e.entry_date = changes["entry_date"]
    if changes.get("category_id"):
        _category(ctx, changes["category_id"], e.direction)
        e.category_id = changes["category_id"]
    if changes.get("amount") is not None:
        e.amount = to_paise(changes["amount"])
    if changes.get("mode"):
        e.mode = changes["mode"]
    if "note" in changes:
        e.note = nfc(changes["note"])
    ctx.db.flush()
    _history(ctx, e, "update")
    audit.from_ctx(ctx, "cash_entry.updated", "cash_entry", e.id, {"before": before, "after": _snapshot(e)})
    ctx.db.commit()
    return e


def delete(ctx: Ctx, entry_id: uuid.UUID) -> None:
    e = ctx.db.get(CashEntry, entry_id)
    if e is None or e.deleted_at is not None:
        raise AppError("ENTRY_NOT_FOUND", 404)
    e.deleted_at = now()
    ctx.db.flush()
    _history(ctx, e, "delete")
    audit.from_ctx(ctx, "cash_entry.deleted", "cash_entry", e.id, _snapshot(e))
    ctx.db.commit()


def history(ctx: Ctx, entry_id: uuid.UUID) -> list[CashEntryHistory]:
    return list(ctx.db.scalars(
        select(CashEntryHistory).where(CashEntryHistory.cash_entry_id == entry_id)
        .order_by(CashEntryHistory.created_at)
    ))


def serialize(e: CashEntry) -> dict[str, Any]:
    return {"id": e.id, "entry_date": e.entry_date, "direction": e.direction, "category_id": e.category_id,
            "amount": from_paise(e.amount), "mode": e.mode, "note": e.note, "version": e.version,
            "created_at": e.created_at}


def categories(ctx: Ctx, include_inactive: bool = False) -> list[Category]:
    stmt = select(Category).order_by(Category.kind, Category.sort_order, Category.name_en)
    if not include_inactive:
        stmt = stmt.where(Category.is_active)
    return list(ctx.db.scalars(stmt))


def save_category(ctx: Ctx, category_id: uuid.UUID | None, *, name_en: str, name_ta: str, kind: str,
                  sort_order: int, is_active: bool) -> Category:
    if category_id:
        cat = ctx.db.get(Category, category_id)
        if cat is None:
            raise AppError("CATEGORY_NOT_FOUND", 404)
    else:
        cat = Category(kind=kind)
        ctx.db.add(cat)
    cat.name_en, cat.name_ta = nfc(name_en) or "", nfc(name_ta) or ""
    cat.sort_order, cat.is_active = sort_order, is_active
    ctx.db.flush()
    audit.from_ctx(ctx, "category.saved", "category", cat.id, {"name_en": cat.name_en, "name_ta": cat.name_ta,
                                                               "active": is_active})
    ctx.db.commit()
    return cat
