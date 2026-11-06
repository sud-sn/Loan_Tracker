"""Analytics star schema (Phase 4): after real activity the facts must agree with the ledger to the
paisa, the borrower dimension holds the profile but never Aadhaar, phone or address, and the
read-only role can read analytics but nothing else. Invented data only."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text

from tests.conftest import Api, make_borrower, make_loan, pay

D = Decimal


def activity(owner: Api) -> None:
    b = make_borrower(owner, occupation="Auto driver", town="Melur", district="Madurai", pincode="625106")
    a = owner.post(
        "/api/v1/loans",
        json={
            "borrower_id": b["id"],
            "idempotency_key": "an-loan-0001",
            "terms": {"principal": "100000", "rate": "2", "term_value": 12, "disbursal_date": "2026-09-04"},
            "charges": [
                {"kind": "processing_fee", "amount": "2000"},
                {"kind": "insurance", "amount": "3000", "treatment": "added"},
            ],
            "security": [
                {
                    "kind": "vehicle",
                    "registration_no": "TN 64 AA 1111",
                    "on_road_price": "300000",
                    "vehicle_type": "three_wheeler",
                }
            ],
        },
    ).json()
    assert pay(owner, a["id"], "9600").status_code == 201
    owner.post(f"/api/v1/loans/{a['id']}/fees", json={"kind": "bounce", "amount": "500"})
    assert pay(owner, a["id"], "10000").status_code == 201
    owner.post(f"/api/v1/loans/{a['id']}/prepay", json={"amount": "20000", "idempotency_key": "an-prepay-01"})
    b2 = make_borrower(owner)
    flat = make_loan(owner, b2["id"], method="flat", disbursal_date="2026-10-30")
    reversed_payment = pay(owner, flat["id"], "1000").json()
    owner.step_up()
    owner.post(f"/api/v1/payments/{reversed_payment['id']}/reverse", json={"reason": "entered twice"})
    total = owner.get(f"/api/v1/loans/{flat['id']}/settlement", params={"foreclosure_charge": "0"}).json()["total"]
    owner.post(
        f"/api/v1/loans/{flat['id']}/settle",
        json={"expected_total": total, "foreclosure_charge": "0", "idempotency_key": "an-settle-01"},
    )
    make_loan(owner, b2["id"], frequency="quarterly", method="interest_only", disbursal_date="2026-06-04")
    food = next(c for c in owner.get("/api/v1/categories").json() if c["name_en"] == "Food")
    r = owner.post(
        "/api/v1/cash-entries",
        json={"direction": "out", "category_id": food["id"], "amount": "350", "entry_date": "2026-11-04"},
    )
    assert r.status_code == 201, r.text


def one(db, sql: str) -> Decimal:  # type: ignore[no-untyped-def]
    return D(str(db.execute(text(sql)).scalar() or 0))


def test_facts_reconcile_with_the_ledger(owner: Api, db) -> None:  # type: ignore[no-untyped-def]
    activity(owner)
    r = owner.post("/api/v1/analytics/refresh")
    assert r.status_code == 200, r.text
    assert r.json()["rows"]["fact_payment"] >= 6 and r.json()["refreshed_at"]

    # Payments: the same money, a reversal negative, and each split adds up.
    assert one(db, "SELECT sum(amount) FROM analytics.fact_payment") == one(
        db, "SELECT sum(CASE WHEN kind = 'reversal' THEN -amount ELSE amount END) / 100.0 FROM payment"
    )
    assert (
        one(db, "SELECT count(*) FROM analytics.fact_payment WHERE principal + interest + late_fee + charges <> amount") == 0
    )
    # Loans given, charges, and what is still unpaid per loan.
    assert one(db, "SELECT sum(principal) FROM analytics.fact_disbursement") == one(
        db, "SELECT sum(principal) / 100.0 FROM loan"
    )
    assert one(db, "SELECT sum(charges_taken_out) FROM analytics.fact_disbursement") == D("2000")
    assert one(db, "SELECT sum(due) FROM analytics.fact_charge") == one(
        db, "SELECT sum(amount - paid - waived) / 100.0 FROM loan_fee"
    )
    assert (
        one(
            db,
            """SELECT count(*) FROM loan l JOIN (SELECT loan_key, sum(unpaid) AS u FROM analytics.fact_installment
                      GROUP BY loan_key) f ON f.loan_key = l.id WHERE l.status = 'active' AND f.u <> l.outstanding / 100.0""",
        )
        == 0
    )
    # This month's snapshot agrees with what each active loan still owes.
    assert (
        one(
            db,
            """SELECT count(*) FROM loan l JOIN analytics.fact_loan_month m ON m.loan_key = l.id
                      AND m.month_end_key = 20261130
                      WHERE l.status = 'active' AND m.principal_outstanding <> l.principal_outstanding / 100.0""",
        )
        == 0
    )
    assert one(db, "SELECT count(*) FROM analytics.fact_loan_month WHERE dpd_bucket <> '0 current'") >= 1
    # Cash flow matches the daily log, with the expense's category.
    assert one(db, "SELECT sum(amount) FROM analytics.fact_cash_flow WHERE direction = 'out'") == one(
        db, "SELECT sum(amount) / 100.0 FROM daily_log WHERE direction = 'out'"
    )
    assert one(db, "SELECT count(*) FROM analytics.fact_cash_flow WHERE category_en IS NOT NULL") == 1
    # Dimensions.
    row = db.execute(
        text("SELECT occupation, town, district, pincode FROM analytics.dim_borrower WHERE occupation IS NOT NULL")
    ).one()
    assert tuple(row) == ("Auto driver", "Melur", "Madurai", "625106")
    assert one(db, "SELECT count(*) FROM analytics.dim_security WHERE vehicle_type = 'three_wheeler'") == 1
    assert one(db, "SELECT fy_start_year FROM analytics.dim_date WHERE date = '2026-04-01'") == 2026
    assert one(db, "SELECT fy_start_year FROM analytics.dim_date WHERE date = '2026-03-31'") == 2025


def test_analytics_never_holds_identity_numbers(db) -> None:  # type: ignore[no-untyped-def]
    columns = {
        r[0]
        for r in db.execute(
            text(
                "SELECT a.attname FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'analytics' AND a.attnum > 0"
            )
        )
    }
    assert not {c for c in columns if any(w in c for w in ("aadhaar", "phone", "address", "password", "totp"))}


def test_read_only_role_sees_analytics_only(db) -> None:  # type: ignore[no-untyped-def]
    db.execute(text("SET ROLE analytics_reader"))
    assert db.execute(text("SELECT count(*) FROM analytics.dim_loan")).scalar() is not None
    with pytest.raises(Exception, match="permission denied"):
        db.execute(text("SELECT count(*) FROM public.borrower"))
    db.rollback()
    db.execute(text("SET ROLE analytics_reader"))
    with pytest.raises(Exception, match="permission denied|must be owner"):
        db.execute(text("SELECT analytics.refresh()"))
    db.rollback()


def test_only_the_owner_refreshes(staff: Api) -> None:
    assert staff.post("/api/v1/analytics/refresh").status_code == 403
    assert staff.get("/api/v1/analytics/status").status_code == 403
