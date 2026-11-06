"""Home page: daybook, quick-add entries, due lists and dashboard cards (PRD sections 6 and 7)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core import cache, clock, i18n
from app.core.errors import AppError
from app.deps import CtxDep, OwnerCtx, StepUpCtx
from app.schemas.common import CashMode, Ok, PositiveMoney
from app.services import cash, daybook, dues, pdf, reports

router = APIRouter(tags=["home"])


class CashEntryIn(BaseModel):
    direction: Literal["in", "out"]
    category_id: uuid.UUID
    amount: PositiveMoney
    entry_date: date | None = None
    mode: CashMode = "cash"
    note: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, max_length=80)


class CashEntryUpdate(BaseModel):
    version: int
    category_id: uuid.UUID | None = None
    amount: PositiveMoney | None = None
    entry_date: date | None = None
    mode: CashMode | None = None
    note: str | None = Field(default=None, max_length=500)


class CashEntryOut(BaseModel):
    id: uuid.UUID
    entry_date: date
    direction: Literal["in", "out"]
    category_id: uuid.UUID
    amount: Decimal
    mode: str
    note: str | None
    version: int
    created_at: Any


class CategoryIn(BaseModel):
    name_en: str = Field(min_length=1, max_length=60)
    name_ta: str = Field(min_length=1, max_length=60)
    kind: Literal["expense", "income"]
    sort_order: int = 0
    is_active: bool = True


class CategoryOut(CategoryIn):
    id: uuid.UUID


@router.get("/daybook")
def get_daybook(ctx: CtxDep, on: date | None = None) -> dict[str, Any]:
    return daybook.day(ctx.db, ctx.business, on or clock.today())


@router.get("/daybook/export")
def export_daybook(ctx: StepUpCtx, start: date, end: date, fmt: Literal["csv", "pdf"] = "pdf",
                   lang: Literal["en", "ta"] | None = None) -> Response:
    if end < start or (end - start).days > 366:
        raise AppError("RANGE_INVALID", 422)
    language = lang or ctx.lang
    def t(key: str, **kw: Any) -> str:
        return i18n.t(language, key, **kw)

    lines = daybook.entries(ctx.db, start, end)
    opening = daybook.balance_before(ctx.db, ctx.business, start)
    totals = daybook.totals(ctx.db, start, end)
    headers = [t("report.date"), t("daybook.in") + " / " + t("daybook.out"), t("report.borrower"), t("receipt.loan"),
               t("receipt.mode"), t("receipt.principal"), t("receipt.interest"), t("report.amount")]
    kinds = {"payment": "daybook.payment", "reversal": "daybook.reversal", "settlement": "daybook.settlement",
             "loan": "daybook.loan", "income": "daybook.income", "expense": "daybook.expense",
             "charge": "daybook.charge"}
    rows = []
    for e in lines:
        who = i18n.name(language, e["name_en"], e["name_ta"]) if e["code"] else (
            e["category_ta"] if language == "ta" else e["category_en"])
        rows.append([
            i18n.fmt_date(e["date"]),
            # A charge is named by what it was for (for example "Processing fee").
            (e["category_ta"] if language == "ta" else e["category_en"]) or t(kinds[e["kind"]])
            if e["kind"] == "charge" else t(kinds[e["kind"]]),
            f"{who}{' · ' + e['code'] if e['code'] else ''}",
            e["loan_no"] or "", t("mode." + e["mode"]), i18n.money(e["principal"], False) if e["principal"] else "",
            i18n.money(e["interest"], False) if e["interest"] else "",
            ("-" if e["direction"] == "out" else "") + i18n.money(e["amount"], False),
        ])
    if fmt == "csv":
        body, media = reports.to_csv(headers, rows), "text/csv; charset=utf-8"
    else:
        from app.engine import from_paise

        summary = [(t("daybook.in"), i18n.money(from_paise(totals["in"]))),
                   (t("daybook.out"), i18n.money(from_paise(totals["out"])))]
        if opening is not None:
            summary = [(t("daybook.opening"), i18n.money(from_paise(opening))), *summary,
                       (t("daybook.closing"), i18n.money(from_paise(opening + totals["in"] - totals["out"])))]
        body = pdf.table(language, ctx.business, title=t("daybook.title"),
                         subtitle=t("daybook.range", start=i18n.fmt_date(start), end=i18n.fmt_date(end)),
                         headers=headers, rows=rows, numeric={5, 6, 7}, summary=summary)
        media = "application/pdf"
    from app.services import audit

    audit.from_ctx(ctx, "export.daybook", None, None, {"start": start.isoformat(), "end": end.isoformat(), "fmt": fmt})
    ctx.db.commit()
    ext = "csv" if fmt == "csv" else "pdf"
    return Response(body, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="daybook-{start}-{end}.{ext}"'})


@router.get("/dues")
def list_dues(
    ctx: CtxDep,
    which: Literal["today", "upcoming", "overdue", "long_unpaid"] = "today",
    sort: Literal["overdue_days", "overdue_amount"] = "overdue_days",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    rows, total = dues.list_dues(ctx.db, ctx.business, which, clock.today(), sort=sort, page=page, page_size=page_size)
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


@router.get("/dashboard")
def dashboard(ctx: CtxDep) -> dict[str, Any]:
    today = clock.today()
    return cache.cached(("dashboard", today), lambda: reports.dashboard(ctx.db, ctx.business, today))


@router.get("/cash-entries/{entry_id}/history")
def entry_history(entry_id: uuid.UUID, ctx: CtxDep) -> list[dict[str, Any]]:
    return [{"action": h.action, "version": h.entry_version, "snapshot": h.snapshot, "at": h.created_at}
            for h in cash.history(ctx, entry_id)]


@router.post("/cash-entries", response_model=CashEntryOut, status_code=201)
def create_entry(data: CashEntryIn, ctx: CtxDep) -> dict[str, Any]:
    e = cash.create(ctx, direction=data.direction, category_id=data.category_id, amount=data.amount,
                    entry_date=data.entry_date, mode=data.mode, note=data.note, idempotency_key=data.idempotency_key)
    return cash.serialize(e)


@router.patch("/cash-entries/{entry_id}", response_model=CashEntryOut)
def update_entry(entry_id: uuid.UUID, data: CashEntryUpdate, ctx: CtxDep) -> dict[str, Any]:
    return cash.serialize(cash.update(ctx, entry_id, data.version, data.model_dump(exclude_unset=True)))


@router.delete("/cash-entries/{entry_id}", response_model=Ok)
def delete_entry(entry_id: uuid.UUID, ctx: CtxDep) -> Ok:
    cash.delete(ctx, entry_id)
    return Ok()


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(ctx: CtxDep, include_inactive: bool = False) -> list[Any]:
    return cash.categories(ctx, include_inactive)


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(data: CategoryIn, ctx: OwnerCtx) -> Any:
    return cash.save_category(ctx, None, **data.model_dump())


@router.put("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: uuid.UUID, data: CategoryIn, ctx: OwnerCtx) -> Any:
    return cash.save_category(ctx, category_id, **data.model_dump())
