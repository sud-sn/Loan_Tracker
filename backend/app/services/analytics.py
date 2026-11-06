"""The analytics star schema (Phase 4): refresh it and report its state.

The ``analytics`` schema holds dimension and fact materialized views built from the ledger tables
(see docs/analytics.md). It is read-only and never holds Aadhaar, phone numbers or addresses. It is
rebuilt nightly by the worker and on demand by the owner; charts and ad-hoc queries read from it.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

TABLES = ("dim_date", "dim_borrower", "dim_loan", "dim_security", "fact_installment", "fact_payment",
          "fact_disbursement", "fact_charge", "fact_cash_flow", "fact_loan_month")


def refresh(db: Session) -> dict[str, Any]:
    db.execute(text("SELECT analytics.refresh()"))
    db.commit()
    return status(db)


def status(db: Session) -> dict[str, Any]:
    last = db.execute(text("SELECT refreshed_at, seconds FROM analytics.refresh_log ORDER BY refreshed_at DESC LIMIT 1")).first()
    rows = {t: int(db.scalar(text(f"SELECT count(*) FROM analytics.{t}")) or 0) for t in TABLES}  # noqa: S608 - fixed names
    return {"refreshed_at": last.refreshed_at if last else None, "seconds": float(last.seconds) if last else None,
            "rows": rows}
