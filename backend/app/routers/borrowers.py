from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response
from sqlalchemy import select

from app.core import clock, i18n
from app.core.errors import AppError
from app.deps import CtxDep, OwnerCtx, StepUpCtx
from app.engine import from_paise
from app.models import Loan
from app.repositories import borrowers as repo
from app.schemas.borrowers import (
    BorrowerDetailOut,
    BorrowerIn,
    BorrowerListItem,
    BorrowerOut,
    BorrowerUpdateIn,
    ConsentIn,
    ConsentOut,
    RevealOut,
    SearchResult,
)
from app.schemas.common import Ok, Page
from app.schemas.loans import LoanListItem
from app.services import borrowers as service
from app.services import loans as loan_service
from app.services import pdf

router = APIRouter(tags=["borrowers"])


@router.get("/search", response_model=list[SearchResult])
def search(ctx: CtxDep, q: str = Query(min_length=1, max_length=60)) -> list[dict[str, Any]]:
    digits = "".join(ch for ch in q if ch.isdigit())
    if len(digits) >= 11:  # never search by a full Aadhaar number (PRD section 12)
        raise AppError("SEARCH_TOO_MANY_DIGITS", 422)
    results = repo.search(ctx.db, q, clock.today())
    return [
        {"kind": "loan" if loan else "borrower", "borrower_id": b.id, "loan_id": loan.id if loan else None,
         "loan_no": loan.loan_no if loan else None, "code": b.code, "name_en": b.name_en, "name_ta": b.name_ta,
         "phone": b.phone, "outstanding": from_paise(outstanding), "overdue": overdue, "matched": how}
        for b, outstanding, overdue, how, loan in results
    ]


@router.get("/borrowers", response_model=Page[BorrowerListItem])
def list_borrowers(
    ctx: CtxDep,
    status: Literal["active", "blocked", "closed"] | None = None,
    has_overdue: bool | None = None,
    has_active_loan: bool | None = None,
    sort: Literal["name", "code", "outstanding", "overdue_days"] = "name",
    desc: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
) -> dict[str, Any]:
    rows, total = repo.list_page(ctx.db, clock.today(), status=status, has_overdue=has_overdue,
                                 has_active_loan=has_active_loan, sort=sort, descending=desc, page=page,
                                 page_size=page_size)
    return {
        "items": [
            {"id": r["borrower"].id, "code": r["borrower"].code, "name_en": r["borrower"].name_en,
             "name_ta": r["borrower"].name_ta, "phone": r["borrower"].phone, "status": r["borrower"].status,
             "outstanding": from_paise(r["outstanding"]), "overdue_amount": from_paise(r["overdue_amount"]),
             "overdue_days": r["overdue_days"], "active_loans": r["active_loans"],
             "multiple_overdue": r["overdue_loans"] >= 2, "profile_incomplete": r["borrower"].aadhaar_hash is None}
            for r in rows
        ],
        "total": total, "page": page, "page_size": page_size,
    }


@router.post("/borrowers", response_model=BorrowerOut, status_code=201)
def create_borrower(data: BorrowerIn, ctx: CtxDep) -> dict[str, Any]:
    return service.serialize(service.create(ctx, data))


@router.get("/borrowers/{borrower_id}", response_model=BorrowerDetailOut)
def get_borrower(borrower_id: uuid.UUID, ctx: CtxDep) -> dict[str, Any]:
    return service.detail(ctx.db, service.get(ctx.db, borrower_id))


@router.patch("/borrowers/{borrower_id}", response_model=BorrowerOut)
def update_borrower(borrower_id: uuid.UUID, data: BorrowerUpdateIn, ctx: CtxDep) -> dict[str, Any]:
    return service.serialize(service.update(ctx, borrower_id, data))


@router.delete("/borrowers/{borrower_id}", response_model=Ok)
def delete_borrower(borrower_id: uuid.UUID, ctx: OwnerCtx) -> Ok:
    service.soft_delete(ctx, borrower_id)
    return Ok()


@router.get("/borrowers/{borrower_id}/loans", response_model=list[LoanListItem])
def borrower_loans(borrower_id: uuid.UUID, ctx: CtxDep) -> list[dict[str, Any]]:
    loans = ctx.db.scalars(
        select(Loan).where(Loan.borrower_id == borrower_id, Loan.deleted_at.is_(None))
        .order_by(Loan.status, Loan.disbursal_date.desc())
    ).all()
    out = []
    for ln in loans:
        s = loan_service.serialize(ctx.db, ln, ctx.business)
        out.append({
            "id": ln.id, "loan_no": ln.loan_no, "borrower": s["borrower"], "principal": s["principal"],
            "disbursal_date": ln.disbursal_date, "maturity_date": ln.maturity_date, "method": ln.method,
            "frequency": ln.frequency, "stored_status": ln.status, "status": s["summary"]["status"],
            "outstanding": s["summary"]["total_outstanding"], "overdue_amount": s["summary"]["overdue_amount"],
            "overdue_days": s["summary"]["overdue_days"],
        })
    return out


@router.post("/borrowers/{borrower_id}/reveal-aadhaar", response_model=RevealOut)
def reveal_aadhaar(borrower_id: uuid.UUID, ctx: StepUpCtx) -> RevealOut:
    return RevealOut(aadhaar=service.reveal_aadhaar(ctx, borrower_id))


@router.post("/borrowers/{borrower_id}/consents", response_model=ConsentOut, status_code=201)
def add_consent(borrower_id: uuid.UUID, data: ConsentIn, ctx: CtxDep) -> Any:
    if not data.given:
        raise AppError("CONSENT_REQUIRED", 422)
    return service.add_consent(ctx, borrower_id, data.method, data.language, data.note)


@router.get("/borrowers/{borrower_id}/statement.pdf")
def statement(borrower_id: uuid.UUID, ctx: CtxDep, lang: Literal["en", "ta"] | None = None) -> Response:
    b = service.get(ctx.db, borrower_id)
    language = lang or b.preferred_language
    loans = ctx.db.scalars(
        select(Loan).where(Loan.borrower_id == b.id, Loan.deleted_at.is_(None)).order_by(Loan.disbursal_date)
    ).all()
    detail = service.detail(ctx.db, b)
    body = pdf.render(
        "statement.html", language, ctx.business, b=detail,
        borrower_name=i18n.name(language, b.name_en, b.name_ta),
        loans=[loan_service.serialize(ctx.db, ln, ctx.business, detail=True) for ln in loans],
    )
    return Response(body, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{b.code}-statement.pdf"'})


@router.get("/borrowers/{borrower_id}/export")
def export_borrower(borrower_id: uuid.UUID, ctx: StepUpCtx) -> Any:
    return service.export_data(ctx, borrower_id)


@router.post("/borrowers/{borrower_id}/erase", response_model=Ok)
def erase_borrower(borrower_id: uuid.UUID, ctx: StepUpCtx) -> Ok:
    service.erase(ctx, borrower_id)
    return Ok()
