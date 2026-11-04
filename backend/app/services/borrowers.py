"""Borrower management (PRD section 3) and privacy workflows (PRD section 12)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core import clock
from app.core.errors import AppError
from app.core.text import mask_aadhaar, nfc, normalize_aadhaar, normalize_phone, search_key
from app.deps import Ctx
from app.engine import from_paise
from app.models import Borrower, Consent, Document, Guarantor, Loan
from app.repositories import borrowers as repo
from app.repositories import counters
from app.schemas.borrowers import BorrowerIn, BorrowerUpdateIn, GuarantorIn
from app.security import crypto
from app.security.tokens import now
from app.services import audit


def _phone(value: str | None, field: str = "phone") -> str | None:
    try:
        return normalize_phone(value)
    except ValueError as exc:
        raise AppError("PHONE_INVALID", 422, field=field) from exc


def _aadhaar(value: str) -> str:
    try:
        return normalize_aadhaar(value)
    except ValueError as exc:
        raise AppError(str(exc), 422, field="aadhaar") from None


def duplicates(db: Session, *, aadhaar_hash: bytes | None, phone: str | None,
               exclude: uuid.UUID | None = None) -> list[dict[str, Any]]:
    conditions = []
    if aadhaar_hash:
        conditions.append(Borrower.aadhaar_hash == aadhaar_hash)
    if phone:
        conditions.append(Borrower.phone == phone)
    if not conditions:
        return []
    stmt = select(Borrower).where(or_(*conditions), Borrower.deleted_at.is_(None))
    if exclude:
        stmt = stmt.where(Borrower.id != exclude)
    return [
        {"code": b.code, "name_en": b.name_en, "name_ta": b.name_ta,
         "match": "aadhaar" if aadhaar_hash and b.aadhaar_hash == aadhaar_hash else "phone"}
        for b in db.scalars(stmt.limit(10))
    ]


def _guard_duplicates(ctx: Ctx, matches: list[dict[str, Any]], confirmed: bool) -> None:
    """Warn on duplicates; only the Owner can proceed after confirming (PRD section 3)."""
    if matches and not (confirmed and ctx.is_owner):
        raise AppError("DUPLICATE_BORROWER", 409, matches=",".join(m["code"] for m in matches),
                       match=matches[0]["match"])


def _set_aadhaar(b: Borrower, number: str) -> None:
    b.aadhaar_encrypted = crypto.encrypt(number, crypto.AADHAAR)
    b.aadhaar_hash = crypto.aadhaar_hmac(number)
    b.aadhaar_last4 = number[-4:]


def _set_guarantors(db: Session, b: Borrower, items: list[GuarantorIn]) -> None:
    for g in list(b.guarantors):
        db.delete(g)
    b.guarantors = [Guarantor(name=nfc(g.name) or "", phone=_phone(g.phone, "guarantor_phone"),
                              relation=nfc(g.relation)) for g in items]


def create(ctx: Ctx, data: BorrowerIn) -> Borrower:
    db = ctx.db
    phone = _phone(data.phone)
    number = _aadhaar(data.aadhaar)
    digest = crypto.aadhaar_hmac(number)
    _guard_duplicates(ctx, duplicates(db, aadhaar_hash=digest, phone=phone), data.confirm_duplicate)
    b = Borrower(
        code=counters.next_borrower_code(db),
        name_en=nfc(data.name_en), name_ta=nfc(data.name_ta), relation_name=nfc(data.relation_name),
        phone=phone, alt_phone=_phone(data.alt_phone, "alt_phone"), address=nfc(data.address),
        preferred_language=data.preferred_language, notes=data.notes, created_by=ctx.user.id,
    )
    b.name_latin = search_key(b.name_en, b.name_ta)
    _set_aadhaar(b, number)
    db.add(b)
    db.flush()
    _set_guarantors(db, b, data.guarantors)
    db.add(Consent(borrower_id=b.id, notice_version=ctx.business.consent_notice_version,
                   language=data.consent.language, method=data.consent.method, recorded_by=ctx.user.id,
                   note=data.consent.note))
    audit.from_ctx(ctx, "borrower.created", "borrower", b.id, {
        "code": b.code, "name_en": b.name_en, "name_ta": b.name_ta, "aadhaar_last4": b.aadhaar_last4,
        "duplicate_confirmed": data.confirm_duplicate,
    })
    db.commit()
    return b


def get(db: Session, borrower_id: uuid.UUID) -> Borrower:
    b = db.scalars(
        select(Borrower).options(selectinload(Borrower.guarantors))
        .where(Borrower.id == borrower_id, Borrower.deleted_at.is_(None))
    ).first()
    if b is None:
        raise AppError("BORROWER_NOT_FOUND", 404)
    return b


def update(ctx: Ctx, borrower_id: uuid.UUID, data: BorrowerUpdateIn) -> Borrower:
    db = ctx.db
    b = get(db, borrower_id)
    if b.version != data.version:
        raise AppError("EDIT_CONFLICT", 409)
    if b.erased_at:
        raise AppError("BORROWER_ERASED", 409)
    changes: dict[str, Any] = {}
    fields = data.model_fields_set
    for name in ("name_en", "name_ta", "relation_name", "address"):
        if name in fields:
            value = nfc(getattr(data, name))
            if value != getattr(b, name):
                changes[name] = [getattr(b, name), value]
                setattr(b, name, value)
    for name in ("phone", "alt_phone"):
        if name in fields:
            value = _phone(getattr(data, name), name)
            if name == "phone" and value is None:
                raise AppError("PHONE_INVALID", 422, field="phone")
            if value != getattr(b, name):
                changes[name] = [getattr(b, name), value]
                setattr(b, name, value)
    for name in ("preferred_language", "status", "notes"):
        if name in fields and getattr(data, name) is not None and getattr(data, name) != getattr(b, name):
            changes[name] = [getattr(b, name), getattr(data, name)]
            setattr(b, name, getattr(data, name))
    if not (b.name_en or b.name_ta):
        raise AppError("NAME_REQUIRED", 422)
    new_hash = None
    if "aadhaar" in fields and data.aadhaar:
        number = _aadhaar(data.aadhaar)
        new_hash = crypto.aadhaar_hmac(number)
        if new_hash != b.aadhaar_hash:
            _set_aadhaar(b, number)
            changes["aadhaar_last4"] = b.aadhaar_last4
    if "phone" in changes or new_hash:
        _guard_duplicates(ctx, duplicates(db, aadhaar_hash=new_hash, phone=b.phone if "phone" in changes else None,
                                          exclude=b.id), data.confirm_duplicate)
    if data.guarantors is not None:
        _set_guarantors(db, b, data.guarantors)
        changes["guarantors"] = len(data.guarantors)
    b.name_latin = search_key(b.name_en, b.name_ta)
    audit.from_ctx(ctx, "borrower.updated", "borrower", b.id, changes)
    db.commit()
    return b


def serialize(b: Borrower) -> dict[str, Any]:
    return {
        "id": b.id, "code": b.code, "name_en": b.name_en, "name_ta": b.name_ta, "relation_name": b.relation_name,
        "phone": b.phone, "alt_phone": b.alt_phone, "aadhaar_masked": mask_aadhaar(b.aadhaar_last4),
        "address": b.address, "preferred_language": b.preferred_language, "status": b.status, "notes": b.notes,
        "profile_incomplete": b.aadhaar_hash is None, "version": b.version, "created_at": b.created_at,
        "guarantors": [{"id": g.id, "name": g.name, "phone": g.phone, "relation": g.relation} for g in b.guarantors],
    }


def detail(db: Session, b: Borrower) -> dict[str, Any]:
    totals = repo.borrower_totals(db, b.id, clock.today())
    consents = db.scalars(select(Consent).where(Consent.borrower_id == b.id).order_by(Consent.created_at.desc())).all()
    return {
        **serialize(b),
        "totals": {**totals, "outstanding": from_paise(totals["outstanding"]),
                   "overdue_amount": from_paise(totals["overdue_amount"])},
        "consents": [{"id": c.id, "notice_version": c.notice_version, "language": c.language, "method": c.method,
                      "note": c.note, "created_at": c.created_at} for c in consents],
    }


def reveal_aadhaar(ctx: Ctx, borrower_id: uuid.UUID) -> str:
    b = get(ctx.db, borrower_id)
    if not b.aadhaar_encrypted:
        raise AppError("AADHAAR_MISSING", 404)
    number = crypto.decrypt(b.aadhaar_encrypted, crypto.AADHAAR)
    audit.from_ctx(ctx, "borrower.aadhaar_revealed", "borrower", b.id, {"code": b.code})
    ctx.db.commit()
    return number


def add_consent(ctx: Ctx, borrower_id: uuid.UUID, method: str, language: str, note: str | None) -> Consent:
    b = get(ctx.db, borrower_id)
    c = Consent(borrower_id=b.id, notice_version=ctx.business.consent_notice_version, language=language,
                method=method, recorded_by=ctx.user.id, note=note)
    ctx.db.add(c)
    audit.from_ctx(ctx, "borrower.consent_recorded", "borrower", b.id, {"method": method, "language": language})
    ctx.db.commit()
    return c


def soft_delete(ctx: Ctx, borrower_id: uuid.UUID) -> None:
    """A borrower with any loan cannot be deleted; use Closed (PRD section 3)."""
    b = get(ctx.db, borrower_id)
    if ctx.db.scalar(select(func.count()).select_from(Loan).where(Loan.borrower_id == b.id)):
        raise AppError("BORROWER_HAS_LOANS", 409)
    b.deleted_at = now()
    audit.from_ctx(ctx, "borrower.deleted", "borrower", b.id, {"code": b.code})
    ctx.db.commit()


def export_data(ctx: Ctx, borrower_id: uuid.UUID) -> dict[str, Any]:
    """DPDP access request: everything held about one borrower (Aadhaar masked)."""
    from app.services import loans as loan_service

    b = get(ctx.db, borrower_id)
    loans = ctx.db.scalars(select(Loan).where(Loan.borrower_id == b.id, Loan.deleted_at.is_(None))).all()
    documents = ctx.db.scalars(
        select(Document).where(Document.owner_type == "borrower", Document.owner_id == b.id,
                               Document.deleted_at.is_(None))
    ).all()
    audit.from_ctx(ctx, "borrower.exported", "borrower", b.id, {"code": b.code})
    ctx.db.commit()
    return {
        "borrower": detail(ctx.db, b),
        "loans": [loan_service.serialize(ctx.db, ln, ctx.business, detail=True) for ln in loans],
        "documents": [{"type": d.doc_type, "name": d.original_name, "uploaded": d.created_at} for d in documents],
    }


def erase(ctx: Ctx, borrower_id: uuid.UUID) -> None:
    """DPDP erasure, subject to records the lender must keep (retention after loan closure)."""
    db = ctx.db
    b = get(db, borrower_id)
    loans = db.scalars(select(Loan).where(Loan.borrower_id == b.id, Loan.deleted_at.is_(None))).all()
    if any(ln.status == "active" for ln in loans):
        raise AppError("ERASE_BLOCKED_ACTIVE_LOAN", 409)
    keep_until = max((ln.closed_on for ln in loans if ln.closed_on), default=None)
    if keep_until and keep_until + timedelta(days=365 * ctx.business.retention_years) > clock.today():
        raise AppError("ERASE_BLOCKED_RETENTION", 409,
                       until=(keep_until + timedelta(days=365 * ctx.business.retention_years)).isoformat())
    b.name_en, b.name_ta, b.relation_name, b.name_latin = "[erased]", None, None, ""
    b.phone = b.alt_phone = b.address = b.notes = None
    b.aadhaar_encrypted = b.aadhaar_hash = None
    b.aadhaar_last4 = None
    b.erased_at = now()
    b.status = "closed"
    for g in list(b.guarantors):
        db.delete(g)
    for d in db.scalars(select(Document).where(Document.owner_type == "borrower", Document.owner_id == b.id)):
        if d.deleted_at is None:
            d.deleted_at, d.purge_after = now(), now()
    audit.from_ctx(ctx, "borrower.erased", "borrower", b.id, {"code": b.code})
    db.commit()
