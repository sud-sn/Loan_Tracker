"""Borrower queries: search, list with totals, per-borrower totals."""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any, Literal

from sqlalchemy import Select, and_, func, literal, or_, select, text
from sqlalchemy.orm import Session

from app.core.text import has_tamil, phonetic_key
from app.models import Borrower, Loan, ScheduleItem

SortKey = Literal["name", "code", "outstanding", "overdue_days"]


def loan_totals(today: date) -> Any:
    """Per-borrower outstanding (cached on loan) and active-loan counts."""
    return (
        select(
            Loan.borrower_id.label("borrower_id"),
            func.coalesce(func.sum(Loan.outstanding).filter(Loan.status == "active"), 0).label("outstanding"),
            func.count().filter(Loan.status == "active").label("active_loans"),
            func.count().filter(Loan.status != "active").label("closed_loans"),
            func.max(Loan.last_payment_on).label("last_payment_on"),
        )
        .where(Loan.deleted_at.is_(None))
        .group_by(Loan.borrower_id)
        .subquery()
    )


def overdue_totals(today: date) -> Any:
    """Overdue amounts from unpaid past-due installments (served by the partial index)."""
    unpaid = (
        ScheduleItem.principal_part + ScheduleItem.interest_part - ScheduleItem.paid_principal
        - ScheduleItem.paid_interest - ScheduleItem.waived_principal - ScheduleItem.waived_interest
    )
    per_loan = (
        select(
            Loan.borrower_id.label("borrower_id"),
            Loan.id.label("loan_id"),
            func.sum(unpaid).label("amount"),
            func.min(ScheduleItem.due_date).label("oldest"),
        )
        .join(Loan, Loan.id == ScheduleItem.loan_id)
        .where(~ScheduleItem.settled, ScheduleItem.due_date < today, Loan.status == "active",
               Loan.deleted_at.is_(None))
        .group_by(Loan.borrower_id, Loan.id)
        .subquery()
    )
    return (
        select(
            per_loan.c.borrower_id,
            func.sum(per_loan.c.amount).label("overdue_amount"),
            func.min(per_loan.c.oldest).label("oldest_overdue"),
            func.count().label("overdue_loans"),
        )
        .group_by(per_loan.c.borrower_id)
        .subquery()
    )


def list_query(
    today: date, *, status: str | None, has_overdue: bool | None, has_active_loan: bool | None, sort: SortKey,
    descending: bool,
) -> Select[Any]:
    lt, od = loan_totals(today), overdue_totals(today)
    overdue_days = func.coalesce(literal(today) - od.c.oldest_overdue, 0)
    stmt = (
        select(
            Borrower,
            func.coalesce(lt.c.outstanding, 0).label("outstanding"),
            func.coalesce(od.c.overdue_amount, 0).label("overdue_amount"),
            overdue_days.label("overdue_days"),
            func.coalesce(lt.c.active_loans, 0).label("active_loans"),
            func.coalesce(od.c.overdue_loans, 0).label("overdue_loans"),
        )
        .outerjoin(lt, lt.c.borrower_id == Borrower.id)
        .outerjoin(od, od.c.borrower_id == Borrower.id)
        .where(Borrower.deleted_at.is_(None))
    )
    if status:
        stmt = stmt.where(Borrower.status == status)
    if has_overdue is not None:
        stmt = stmt.where(od.c.overdue_amount.is_not(None) if has_overdue else od.c.overdue_amount.is_(None))
    if has_active_loan is not None:
        stmt = stmt.where(lt.c.active_loans > 0 if has_active_loan else func.coalesce(lt.c.active_loans, 0) == 0)
    # Tamil-aware collation from ICU (PRD section 9): Tamil names sort in Tamil alphabet order.
    name_sort = func.coalesce(Borrower.name_en, Borrower.name_ta).collate("ta-IN-x-icu")
    order = {
        "name": name_sort,
        "code": Borrower.code,
        "outstanding": func.coalesce(lt.c.outstanding, 0),
        "overdue_days": overdue_days,
    }[sort]
    return stmt.order_by(order.desc() if descending else order.asc(), Borrower.code)


_CODE = re.compile(r"^(?:brw-?)?0*(\d{1,6})$", re.I)
_LOAN = re.compile(r"^ln-?(\d{4})-?0*(\d{1,6})$", re.I)


def search(db: Session, q: str, today: date, limit: int = 20) -> list[tuple[Borrower, int, bool, str, Loan | None]]:
    """Find borrowers by name (either script, partial, typo-tolerant), code, phone, loan number or
    the last 4 Aadhaar digits. Returns (borrower, outstanding paise, overdue, matched-on, loan)."""
    q = q.strip()
    if not q:
        return []
    digits = re.sub(r"\D", "", q)
    base = select(Borrower).where(Borrower.deleted_at.is_(None))
    found: list[tuple[Borrower, str, Loan | None]] = []

    if m := _LOAN.match(q.replace(" ", "")):
        loan_no = f"LN-{m.group(1)}-{int(m.group(2)):06d}"
        for loan_row, borrower in db.execute(
            select(Loan, Borrower).join(Borrower, Borrower.id == Loan.borrower_id)
            .where(Loan.loan_no == loan_no, Loan.deleted_at.is_(None))
        ).all():
            found.append((borrower, "loan_no", loan_row))
    elif q.upper().startswith("BRW") or (digits == q and len(digits) <= 3):
        if m := _CODE.match(q.replace(" ", "")):
            code = f"BRW-{int(m.group(1)):06d}"
            found += [(b, "code", None) for b in db.scalars(base.where(Borrower.code == code))]
    elif digits and len(digits) == len(re.sub(r"[\s+-]", "", q)):
        if len(digits) == 4:
            found += [(b, "aadhaar_last4", None) for b in db.scalars(base.where(Borrower.aadhaar_last4 == digits).limit(limit))]
            found += [(b, "code", None) for b in db.scalars(base.where(Borrower.code == f"BRW-{int(digits):06d}"))]
        if 4 <= len(digits) <= 10:
            found += [(b, "phone", None) for b in db.scalars(
                base.where(or_(Borrower.phone.like(f"%{digits}%"), Borrower.alt_phone.like(f"%{digits}%"))).limit(limit)
            )]
        if len(digits) in (5, 6):
            found += [(b, "code", None) for b in db.scalars(base.where(Borrower.code == f"BRW-{int(digits):06d}"))]
    else:
        pattern = f"%{q.lower()}%"
        key = phonetic_key(q)
        conditions: list[Any] = (
            [Borrower.name_ta.like(f"%{q}%")] if has_tamil(q) else [func.lower(Borrower.name_en).like(pattern)]
        )
        if len(key) >= 2:
            conditions.append(Borrower.name_latin.like(f"%{key}%"))
        if len(q) >= 3 and not has_tamil(q):
            # Typo tolerance: trigram word similarity on the English name and the phonetic key. The
            # threshold is lowered for this transaction only, and the GIN trigram indexes still apply.
            db.execute(text("SET LOCAL pg_trgm.word_similarity_threshold = 0.45"))
            conditions.append(text("lower(borrower.name_en) %> :q").bindparams(q=q.lower()))
            if len(key) >= 3:
                conditions.append(text("borrower.name_latin %> :k").bindparams(k=key))
        score = func.greatest(
            func.word_similarity(q.lower(), func.lower(func.coalesce(Borrower.name_en, ""))),
            func.word_similarity(q, func.coalesce(Borrower.name_ta, "")),
            func.word_similarity(key or q, Borrower.name_latin),
        )
        found += [(b, "name", None) for b in db.scalars(base.where(or_(*conditions)).order_by(score.desc()).limit(limit))]

    seen: set[tuple[uuid.UUID, uuid.UUID | None]] = set()
    unique: list[tuple[Borrower, str, Loan | None]] = []
    for b, how, hit in found:
        marker = (b.id, hit.id if hit else None)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append((b, how, hit))
    unique = unique[:limit]
    ids = [b.id for b, _, _ in unique]
    if not ids:
        return []
    totals = dict(
        db.execute(
            select(Loan.borrower_id, func.sum(Loan.outstanding))
            .where(Loan.borrower_id.in_(ids), Loan.status == "active", Loan.deleted_at.is_(None))
            .group_by(Loan.borrower_id)
        ).all()
    )
    overdue_ids = set(
        db.scalars(
            select(Loan.borrower_id).join(ScheduleItem, ScheduleItem.loan_id == Loan.id)
            .where(Loan.borrower_id.in_(ids), Loan.status == "active", ~ScheduleItem.settled,
                   ScheduleItem.due_date < today)
            .distinct()
        )
    )
    return [(b, int(totals.get(b.id) or 0), b.id in overdue_ids, how, loan) for b, how, loan in unique]


def borrower_totals(db: Session, borrower_id: uuid.UUID, today: date) -> dict[str, Any]:
    lt, od = loan_totals(today), overdue_totals(today)
    row = db.execute(
        select(
            func.coalesce(lt.c.outstanding, 0), func.coalesce(od.c.overdue_amount, 0), od.c.oldest_overdue,
            func.coalesce(lt.c.active_loans, 0), func.coalesce(lt.c.closed_loans, 0),
            func.coalesce(od.c.overdue_loans, 0), lt.c.last_payment_on,
        )
        .select_from(Borrower)
        .outerjoin(lt, lt.c.borrower_id == Borrower.id)
        .outerjoin(od, and_(od.c.borrower_id == Borrower.id))
        .where(Borrower.id == borrower_id)
    ).one()
    outstanding, overdue, oldest, active, closed, overdue_loans, last = row
    return {
        "outstanding": int(outstanding), "overdue_amount": int(overdue),
        "overdue_days": (today - oldest).days if oldest else 0, "active_loans": int(active),
        "closed_loans": int(closed), "overdue_loans": int(overdue_loans), "last_payment_on": last,
    }
