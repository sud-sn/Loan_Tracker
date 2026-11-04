"""Loans, payments, reversal, idempotency, overdue (acceptance checks 2, 4, 5, 10, 11)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db import get_engine
from app.services import ledger
from tests.conftest import TODAY, Api, make_borrower, make_loan, pay


def test_reducing_loan_matches_prd_fixture(owner: Api) -> None:
    b = make_borrower(owner)
    loan = make_loan(owner, b["id"])
    assert loan["loan_no"] == "LN-2026-000001"
    rows = loan["schedule"]
    assert rows[0]["installment"] == "9455.96" and rows[0]["interest_part"] == "2000.00"
    assert rows[-1]["installment"] == "9455.97" and rows[-1]["closing_balance"] == "0.00"
    assert sum(Decimal(r["principal_part"]) for r in rows) == Decimal("100000.00")
    assert loan["total_interest"] == "13471.53"


@pytest.mark.parametrize(("terms", "first", "interest"), [
    ({"method": "flat"}, "10333.33", "24000.00"),
    ({"method": "interest_only"}, "2000.00", "24000.00"),
    ({"method": "simple_days", "frequency": "single", "term_value": 90, "term_unit": "days"}, "106000.00", "6000.00"),
])
def test_other_fixtures(owner: Api, terms: dict, first: str, interest: str) -> None:  # type: ignore[type-arg]
    b = make_borrower(owner)
    loan = make_loan(owner, b["id"], **terms)
    assert loan["schedule"][0]["installment"] == first
    assert loan["total_interest"] == interest


def test_fixed_amount_toggle_calculates_the_period(owner: Api) -> None:
    """The borrower wants to pay ₹10,000 a month: the app works out how many months."""
    b = make_borrower(owner)
    preview = owner.post("/api/v1/loans/preview", json={
        "principal": "100000", "rate": "2", "method": "fixed_amount", "fixed_installment": "10000",
        "fixed_style": "flat", "disbursal_date": "2026-01-05"}).json()
    assert preview["installments"] == 13
    assert preview["installment"] == "10000.00"
    assert preview["rows"][0]["interest_part"] == "2000.00"
    assert preview["rows"][0]["principal_part"] == "8000.00"
    loan = make_loan(owner, b["id"], method="fixed_amount", fixed_installment="10000", term_value=None)
    assert loan["installments"] == 13 and loan["method"] == "fixed_amount"
    assert loan["fixed_installment"] == "10000.00"


def test_custom_split_per_installment(owner: Api) -> None:
    b = make_borrower(owner)
    rows = [{"principal_part": "40000", "interest_part": "2000"}, {"principal_part": "60000", "interest_part": "1200"}]
    loan = make_loan(owner, b["id"], method="custom", custom_rows=rows, term_value=None)
    assert [r["installment"] for r in loan["schedule"]] == ["42000.00", "61200.00"]
    bad = owner.post("/api/v1/loans/preview", json={"principal": "100000", "rate": "0", "method": "custom",
                                                    "custom_rows": rows[:1], "disbursal_date": "2026-01-05"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "CUSTOM_PRINCIPAL_MISMATCH"


def test_preview_is_fast(owner: Api) -> None:
    import time

    start = time.perf_counter()
    r = owner.post("/api/v1/loans/preview", json={"principal": "500000", "rate": "1.5", "term_value": 360,
                                                  "disbursal_date": "2026-01-05"})
    assert r.status_code == 200
    assert time.perf_counter() - start < 0.2


def test_rate_above_maximum_warns_before_saving(owner: Api) -> None:
    s = owner.get("/api/v1/settings").json()
    owner.put("/api/v1/settings", json={"version": s["version"], "max_rate_monthly": "1.5"})
    b = make_borrower(owner)
    r = owner.post("/api/v1/loans", json={"borrower_id": b["id"], "idempotency_key": "rate-warn-0001",
                                          "terms": {"principal": "1000", "rate": "2", "term_value": 3,
                                                    "disbursal_date": "2026-10-01"}})
    assert r.status_code == 409 and r.json()["error"]["code"] == "RATE_ABOVE_MAXIMUM"
    r = owner.post("/api/v1/loans", json={"borrower_id": b["id"], "idempotency_key": "rate-warn-0002",
                                          "acknowledge_rate_warning": True,
                                          "terms": {"principal": "1000", "rate": "2", "term_value": 3,
                                                    "disbursal_date": "2026-10-01"}})
    assert r.status_code == 201


def test_payment_allocation_and_split_shown(owner: Api) -> None:
    b = make_borrower(owner)
    loan = make_loan(owner, b["id"])
    r = pay(owner, loan["id"], "12000.00", paid_on="2026-02-05")
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["receipt_no"] == "RCT-2026-000001"
    assert p["allocations"][0] == {"seq": 1, "due_date": "2026-02-05", "penalty_part": "0.00",
                                   "interest_part": "2000.00", "principal_part": "7455.96"}
    assert p["allocations"][1]["interest_part"] == "1850.88"  # the extra goes to the next installment
    assert p["allocations"][1]["principal_part"] == "693.16"
    assert p["balance_after"] == str(Decimal("113471.53") - Decimal("12000.00"))


def test_future_dates_and_overpayment_rejected(owner: Api) -> None:
    b = make_borrower(owner)
    loan = make_loan(owner, b["id"])
    r = pay(owner, loan["id"], "100", paid_on=(TODAY + timedelta(days=1)).isoformat())
    assert r.json()["error"]["code"] == "DATE_IN_FUTURE"
    r = pay(owner, loan["id"], "200000")
    assert r.json()["error"]["code"] == "PAYMENT_EXCEEDS_OUTSTANDING"


def test_idempotency_key_creates_one_payment(owner: Api) -> None:
    b = make_borrower(owner)
    loan = make_loan(owner, b["id"])
    first = pay(owner, loan["id"], "5000.00", key="same-key-0001")
    second = pay(owner, loan["id"], "5000.00", key="same-key-0001")
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"] and second.json()["replayed"] is True
    other = pay(owner, loan["id"], "6000.00", key="same-key-0001")
    assert other.status_code == 409 and other.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    detail = owner.get(f"/api/v1/loans/{loan['id']}").json()
    assert len(detail["payments"]) == 1


def test_simultaneous_payments_do_not_double_allocate(owner: Api) -> None:
    b = make_borrower(owner)
    loan = make_loan(owner, b["id"], principal="1000", term_value=1, rate="0")

    def attempt(i: int) -> int:
        return int(pay(owner, loan["id"], "1000.00", key=f"race-key-{i:04d}").status_code)

    with ThreadPoolExecutor(max_workers=5) as pool:
        codes = list(pool.map(attempt, range(5)))
    assert codes.count(201) == 1  # the loan is fully paid by the first; the rest are refused
    detail = owner.get(f"/api/v1/loans/{loan['id']}").json()
    assert detail["stored_status"] == "closed"
    same = [pay(owner, loan["id"], "10", key="same-race") for _ in range(1)]
    assert same[0].status_code == 409  # loan closed


def test_overdue_partial_and_full_payment(owner: Api) -> None:
    b = make_borrower(owner)
    due = TODAY - timedelta(days=10)
    loan = make_loan(owner, b["id"], disbursal_date=(due - timedelta(days=30)).isoformat(),
                     first_due_date=due.isoformat())

    def overdue_row() -> dict | None:  # type: ignore[type-arg]
        items = owner.get("/api/v1/dues", params={"which": "overdue"}).json()["items"]
        return next((x for x in items if x["loan_id"] == loan["id"]), None)

    row = overdue_row()
    assert row is not None and row["overdue_days"] == 10 and row["amount_due"] == "9455.96"
    assert row["bucket"] == "8_30"
    pay(owner, loan["id"], "3000")
    row = overdue_row()
    assert row is not None and row["amount_due"] == "6455.96" and row["overdue_days"] == 10
    detail = owner.get(f"/api/v1/loans/{loan['id']}").json()
    assert detail["schedule"][0]["status"] == "overdue" and detail["summary"]["status"] == "overdue"
    pay(owner, loan["id"], "6455.96")
    assert overdue_row() is None
    detail = owner.get(f"/api/v1/loans/{loan['id']}").json()
    assert detail["schedule"][0]["status"] == "paid"


def test_due_today_and_upcoming(owner: Api) -> None:
    b = make_borrower(owner)
    loan = make_loan(owner, b["id"], disbursal_date=(TODAY - timedelta(days=30)).isoformat(),
                     first_due_date=TODAY.isoformat())
    today = owner.get("/api/v1/dues", params={"which": "today"}).json()["items"]
    assert [x["loan_id"] for x in today] == [loan["id"]]
    assert today[0]["phone"] == b["phone"] and today[0]["code"] == b["code"]
    b2 = make_borrower(owner)
    soon = make_loan(owner, b2["id"], disbursal_date=(TODAY - timedelta(days=25)).isoformat(),
                     first_due_date=(TODAY + timedelta(days=5)).isoformat())
    upcoming = owner.get("/api/v1/dues", params={"which": "upcoming"}).json()["items"]
    assert soon["id"] in [x["loan_id"] for x in upcoming]


def test_long_unpaid_after_31_days(owner: Api) -> None:
    b = make_borrower(owner)
    loan = make_loan(owner, b["id"], disbursal_date=(TODAY - timedelta(days=31)).isoformat(),
                     first_due_date=(TODAY + timedelta(days=20)).isoformat(), frequency="monthly")
    items = owner.get("/api/v1/dues", params={"which": "long_unpaid"}).json()["items"]
    assert [x["loan_id"] for x in items] == [loan["id"]]
    assert items[0]["days_since_last_payment"] == 31


def test_reversal_reopens_installments_and_keeps_original(owner: Api) -> None:
    b = make_borrower(owner)
    loan = make_loan(owner, b["id"], principal="1000", rate="0", term_value=2)
    p = pay(owner, loan["id"], "1000.00").json()
    assert owner.get(f"/api/v1/loans/{loan['id']}").json()["stored_status"] == "closed"
    r = owner.post(f"/api/v1/payments/{p['id']}/reverse", json={"reason": "cheque bounced"})
    assert r.status_code == 403  # step-up needed
    owner.step_up()
    r = owner.post(f"/api/v1/payments/{p['id']}/reverse", json={"reason": "cheque bounced"})
    assert r.status_code == 200, r.text
    rev = r.json()
    assert rev["kind"] == "reversal" and rev["reversed_of_id"] == p["id"]
    assert rev["allocations"][0]["principal_part"] == "-500.00"
    detail = owner.get(f"/api/v1/loans/{loan['id']}").json()
    assert detail["stored_status"] == "active"
    assert [x["unpaid"] for x in detail["schedule"]] == ["500.00", "500.00"]
    kinds = {x["kind"] for x in detail["payments"]}
    assert kinds == {"payment", "reversal"}
    original = next(x for x in detail["payments"] if x["id"] == p["id"])
    assert original["reversed_by_id"] == rev["id"]
    again = owner.post(f"/api/v1/payments/{p['id']}/reverse", json={"reason": "again"})
    assert again.json()["error"]["code"] == "ALREADY_REVERSED"


def test_early_settlement_waives_future_interest(owner: Api) -> None:
    b = make_borrower(owner)
    loan = make_loan(owner, b["id"], method="flat", disbursal_date="2026-08-20")
    pay(owner, loan["id"], "10333.33", paid_on="2026-09-20")
    pay(owner, loan["id"], "10333.33", paid_on="2026-10-20")
    fig = owner.get(f"/api/v1/loans/{loan['id']}/settlement").json()
    assert Decimal(fig["principal"]) == Decimal("100000") - 2 * Decimal("8333.33")
    # 15 of the 31 days of the current period (20 Oct to 20 Nov) have passed: 2,000 x 15/31.
    assert Decimal(fig["interest"]) == Decimal("967.74")
    assert Decimal(fig["interest_waived"]) == Decimal("2000") * 9 + Decimal("2000") - Decimal("967.74")
    r = owner.post(f"/api/v1/loans/{loan['id']}/settle", json={"expected_total": fig["total"],
                                                              "idempotency_key": "settle-key-0001"})
    assert r.status_code == 200, r.text
    detail = owner.get(f"/api/v1/loans/{loan['id']}").json()
    assert detail["stored_status"] == "closed" and detail["closed_reason"] == "settled_early"
    assert detail["summary"]["total_outstanding"] == "0.00"


def test_write_off_with_reason(owner: Api) -> None:
    b = make_borrower(owner)
    loan = make_loan(owner, b["id"])
    r = owner.post(f"/api/v1/loans/{loan['id']}/write-off", json={"reason": "moved away", "amount_received": "5000",
                                                                 "idempotency_key": "writeoff-key-0001"})
    assert r.status_code == 200, r.text
    assert r.json()["stored_status"] == "written_off"
    assert r.json()["summary"]["total_outstanding"] == "0.00"


def test_ledger_is_append_only_and_sums_are_enforced(owner: Api) -> None:
    b = make_borrower(owner)
    loan = make_loan(owner, b["id"])
    pay(owner, loan["id"], "100")
    engine = get_engine()
    for sql in ("UPDATE payment SET amount = 1", "DELETE FROM payment", "UPDATE audit_log SET action = 'x'",
                "DELETE FROM payment_allocation", "UPDATE schedule_item SET installment = 1",
                "UPDATE loan SET principal = 1"):
        with pytest.raises(Exception, match="append-only|locked"), engine.begin() as conn:
            conn.execute(text(sql))
    with pytest.raises(Exception, match="sum to"), engine.begin() as conn:
        pid = conn.execute(text("SELECT id FROM payment LIMIT 1")).scalar()
        item = conn.execute(text("SELECT id FROM schedule_item LIMIT 1")).scalar()
        conn.execute(text("INSERT INTO payment_allocation (id, payment_id, schedule_item_id, principal_part) "
                          "VALUES (gen_random_uuid(), :p, :i, 5)"), {"p": pid, "i": item})


def test_cached_ledger_columns_rebuild_without_drift(owner: Api, db) -> None:  # type: ignore[no-untyped-def]
    b = make_borrower(owner)
    loan = make_loan(owner, b["id"])
    owner.step_up()
    for amount in ("9455.96", "5000", "12000.50"):
        p = pay(owner, loan["id"], amount).json()
    owner.post(f"/api/v1/payments/{p['id']}/reverse", json={"reason": "typo"})
    pay(owner, loan["id"], "1200.50")
    import uuid

    assert ledger.rebuild_item_cache(db, uuid.UUID(loan["id"]), fix=False) == []


def test_penalty_accrues_separately_and_is_paid_first(owner: Api) -> None:
    b = make_borrower(owner)
    due = TODAY - timedelta(days=10)
    r = owner.post("/api/v1/loans", json={
        "borrower_id": b["id"], "idempotency_key": "penalty-loan-0001",
        "penalty": {"mode": "per_day", "value": "10"},
        "terms": {"principal": "10000", "rate": "2", "term_value": 2, "disbursal_date": (due - timedelta(days=30)).isoformat(),
                  "first_due_date": due.isoformat()}})
    loan = r.json()
    assert loan["summary"]["penalty_outstanding"] == "100.00"
    assert Decimal(loan["summary"]["overdue_amount"]) == Decimal(loan["schedule"][0]["installment"]) + 100
    p = pay(owner, loan["id"], "150").json()
    assert p["allocations"][0]["penalty_part"] == "100.00"
    assert p["allocations"][0]["interest_part"] == "50.00"
