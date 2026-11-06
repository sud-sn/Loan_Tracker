"""Borrower queries: search, list with totals, per-borrower totals."""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any, Literal

from sqlalchemy import func, literal, or_, select, text
from sqlalchemy.orm import Session

from app.core.text import has_tamil, phonetic_key
from app.models import Borrower, Collateral, Loan, ScheduleItem

SortKey = Literal["name", "code", "outstanding", "overdue_days"]


def loan_totals(today: date) -> Any:
    """Per-borrower totals from the loan table alone (cached ledger columns, 200k rows not 2.4M)."""
    overdue = (Loan.status == "active") & (Loan.next_unpaid_due < today)
    return (
        select(
            Loan.borrower_id.label("borrower_id"),
            func.coalesce(func.sum(Loan.outstanding).filter(Loan.status == "active"), 0).label("outstanding"),
            func.count().filter(Loan.status == "active").label("active_loans"),
            func.count().filter(Loan.status != "active").label("closed_loans"),
            func.max(Loan.last_payment_on).label("last_payment_on"),
            func.min(Loan.next_unpaid_due).filter(overdue).label("oldest_overdue"),
            func.count().filter(overdue).label("overdue_loans"),
        )
        .where(Loan.deleted_at.is_(None))
        .group_by(Loan.borrower_id)
        .subquery()
    )


def overdue_amounts(db: Session, borrower_ids: list[uuid.UUID], today: date) -> dict[uuid.UUID, int]:
    """Unpaid past-due principal + interest for a few borrowers (the rows on screen)."""
    if not borrower_ids:
        return {}
    unpaid = (
        ScheduleItem.principal_part + ScheduleItem.interest_part - ScheduleItem.paid_principal
        - ScheduleItem.paid_interest - ScheduleItem.waived_principal - ScheduleItem.waived_interest
    )
    rows = db.execute(
        select(Loan.borrower_id, func.sum(unpaid))
        .join(ScheduleItem, ScheduleItem.loan_id == Loan.id)
        .where(Loan.borrower_id.in_(borrower_ids), Loan.status == "active", Loan.deleted_at.is_(None),
               Loan.next_unpaid_due < today, ~ScheduleItem.settled, ScheduleItem.due_date < today)
        .group_by(Loan.borrower_id)
    )
    return {bid: int(amount) for bid, amount in rows}


def list_page(
    db: Session, today: date, *, status: str | None, has_overdue: bool | None, has_active_loan: bool | None,
    sort: SortKey, descending: bool, page: int, page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    lt = loan_totals(today)
    # Tamil-aware collation from ICU (PRD section 9): Tamil names sort in Tamil alphabet order.
    name_sort = func.coalesce(Borrower.name_en, Borrower.name_ta).collate("ta-IN-x-icu")
    overdue_days = func.coalesce(literal(today) - lt.c.oldest_overdue, 0)
    base = select(Borrower).where(Borrower.deleted_at.is_(None))
    if status:
        base = base.where(Borrower.status == status)
    plain = sort in ("name", "code") and has_overdue is None and has_active_loan is None
    if plain:
        # Page the borrowers first (indexed), then total up only the rows on screen.
        order = name_sort if sort == "name" else Borrower.code
        total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
        borrowers = list(db.scalars(base.order_by(order.desc() if descending else order.asc(), Borrower.code)
                                    .limit(page_size).offset((page - 1) * page_size)))
        ids = [b.id for b in borrowers]
        totals = {r.borrower_id: r for r in db.execute(select(lt).where(lt.c.borrower_id.in_(ids)))} if ids else {}
        rows = [(b, totals.get(b.id)) for b in borrowers]
    else:
        stmt = select(Borrower, lt, func.count().over().label("total")).outerjoin(lt, lt.c.borrower_id == Borrower.id)
        stmt = stmt.where(Borrower.deleted_at.is_(None))
        if status:
            stmt = stmt.where(Borrower.status == status)
        if has_overdue is not None:
            stmt = stmt.where(lt.c.overdue_loans > 0 if has_overdue else func.coalesce(lt.c.overdue_loans, 0) == 0)
        if has_active_loan is not None:
            stmt = stmt.where(lt.c.active_loans > 0 if has_active_loan else func.coalesce(lt.c.active_loans, 0) == 0)
        sort_col: Any = {"name": name_sort, "code": Borrower.code, "outstanding": func.coalesce(lt.c.outstanding, 0),
                         "overdue_days": overdue_days}[sort]
        result = db.execute(stmt.order_by(sort_col.desc() if descending else sort_col.asc(), Borrower.code)
                            .limit(page_size).offset((page - 1) * page_size)).all()
        total = int(result[0].total) if result else 0
        rows = [(r[0], r) for r in result]
    amounts = overdue_amounts(db, [b.id for b, _ in rows], today)
    items = []
    for b, t in rows:
        oldest = t.oldest_overdue if t is not None else None
        items.append({
            "borrower": b, "outstanding": int(t.outstanding) if t is not None else 0,
            "overdue_amount": amounts.get(b.id, 0), "overdue_days": (today - oldest).days if oldest else 0,
            "active_loans": int(t.active_loans) if t is not None else 0,
            "overdue_loans": int(t.overdue_loans) if t is not None else 0,
        })
    return items, int(total)


_CODE = re.compile(r"^(?:brw-?)?0*(\d{1,6})$", re.I)
_LOAN = re.compile(r"^ln-?(\d{4})-?0*(\d{1,6})$", re.I)


def search(db: Session, q: str, today: date, limit: int = 20) -> list[tuple[Borrower, int, bool, str, Loan | None]]:
    """Find borrowers by name (either script, partial, typo-tolerant), code, phone, loan number,
    the last 4 Aadhaar digits or a vehicle registration number (whole, part, or its last 4 digits).
    Returns (borrower, outstanding paise, overdue, matched-on, loan)."""
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
            found += _by_vehicle(db, f"%{digits}", limit)
            found += [(b, "code", None) for b in db.scalars(base.where(Borrower.code == f"BRW-{int(digits):06d}"))]
        if 4 <= len(digits) <= 10:
            found += [(b, "phone", None) for b in db.scalars(
                base.where(or_(Borrower.phone.like(f"%{digits}%"), Borrower.alt_phone.like(f"%{digits}%"))).limit(limit)
            )]
        if len(digits) in (5, 6):
            found += [(b, "code", None) for b in db.scalars(base.where(Borrower.code == f"BRW-{int(digits):06d}"))]
    else:
        plate = re.sub(r"[^A-Z0-9]", "", q.upper())
        if len(plate) >= 4 and re.search(r"[A-Z]", plate) and re.search(r"\d", plate):
            found += _by_vehicle(db, f"%{plate}%", limit)
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


def _by_vehicle(db: Session, pattern: str, limit: int) -> list[tuple[Borrower, str, Loan | None]]:
    """Loans given against a vehicle whose registration (upper case, letters and digits only)
    matches ``pattern``."""
    rows = db.execute(
        select(Borrower, Loan).join(Loan, Loan.borrower_id == Borrower.id)
        .join(Collateral, Collateral.loan_id == Loan.id)
        .where(Collateral.registration_key.like(pattern), Loan.deleted_at.is_(None), Borrower.deleted_at.is_(None))
        .order_by(Loan.created_at.desc()).limit(limit)
    ).all()
    return [(b, "vehicle", loan) for b, loan in rows]


def borrower_totals(db: Session, borrower_id: uuid.UUID, today: date) -> dict[str, Any]:
    lt = loan_totals(today)
    t = db.execute(select(lt).where(lt.c.borrower_id == borrower_id)).first()
    oldest = t.oldest_overdue if t is not None else None
    return {
        "outstanding": int(t.outstanding) if t is not None else 0,
        "overdue_amount": overdue_amounts(db, [borrower_id], today).get(borrower_id, 0),
        "overdue_days": (today - oldest).days if oldest else 0,
        "active_loans": int(t.active_loans) if t is not None else 0,
        "closed_loans": int(t.closed_loans) if t is not None else 0,
        "overdue_loans": int(t.overdue_loans) if t is not None else 0,
        "last_payment_on": t.last_payment_on if t is not None else None,
    }
