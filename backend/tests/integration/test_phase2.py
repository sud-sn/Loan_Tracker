"""Phase 2: part-prepayment with a new schedule, charges after the loan is given, late-fee waiver,
foreclosure charge and rebate choices when closing early. Invented data only."""

from __future__ import annotations

from decimal import Decimal

from app.services import ledger
from tests.conftest import Api, make_borrower, make_loan, pay

D = Decimal


def loan_given(owner: Api, given: str, **terms: object) -> dict:  # type: ignore[type-arg]
    b = make_borrower(owner)
    return make_loan(owner, b["id"], disbursal_date=given, **terms)


def prepay(owner: Api, loan_id: str, amount: str, key: str, mode: str = "reduce_emi") -> object:
    return owner.post(f"/api/v1/loans/{loan_id}/prepay",
                      json={"amount": amount, "mode_of_reschedule": mode, "idempotency_key": key})


def detail(owner: Api, loan_id: str) -> dict:  # type: ignore[type-arg]
    return dict(owner.get(f"/api/v1/loans/{loan_id}").json())


def test_part_prepayment_lowers_the_emi_and_keeps_the_dates(owner: Api, db) -> None:  # type: ignore[no-untyped-def]
    loan = loan_given(owner, "2026-10-30")  # first installment due 30/11, nothing due yet
    old_emi = D(loan["installment_amount"])
    pv = owner.get(f"/api/v1/loans/{loan['id']}/prepay", params={"amount": "20000"}).json()
    assert pv["dues"] == "0.00" and pv["extra"] == "20000.00"
    assert pv["principal_after"] == "80000.00" and pv["new_count"] == 12
    assert D(pv["new_installment"]) < old_emi and D(pv["interest_saved"]) > 0
    r = prepay(owner, loan["id"], "20000", "prepay-0001")
    assert r.status_code == 201, r.text  # type: ignore[attr-defined]
    after = detail(owner, loan["id"])
    rows = after["schedule"]
    assert [x["status"] for x in rows[:12]] == ["rescheduled"] * 12
    new = rows[12:]
    assert len(new) == 12 and [x["due_date"] for x in new] == [x["due_date"] for x in rows[:12]]
    assert sum(D(x["principal_part"]) for x in new) == D("80000")
    assert after["installment_amount"] == pv["new_installment"] and after["installments"] == 12
    assert after["summary"]["principal_outstanding"] == "80000.00"
    assert after["reschedules"][0]["extra"] == "20000.00" and after["reschedules"][0]["mode"] == "reduce_emi"
    # Interest of the period the extra was paid in is split by days: between the new and old figure.
    assert D("1600") < D(new[0]["interest_part"]) < D("2000")
    # Undoing it would break the new schedule.
    pid = r.json()["id"]  # type: ignore[attr-defined]
    owner.step_up()
    rev = owner.post(f"/api/v1/payments/{pid}/reverse", json={"reason": "typing mistake"})
    assert rev.status_code == 409 and rev.json()["error"]["code"] == "PAYMENT_LOCKED_BY_RESCHEDULE"
    assert ledger.rebuild_item_cache(db, __import__("uuid").UUID(loan["id"]), fix=False) == []


def test_part_prepayment_to_finish_sooner_pays_what_is_due_first(owner: Api) -> None:
    loan = loan_given(owner, "2026-09-04")  # installments due 04/10 (overdue) and 04/11 (today)
    pv = owner.get(f"/api/v1/loans/{loan['id']}/prepay", params={"amount": "40000", "mode": "reduce_term"}).json()
    assert D(pv["dues"]) == D("9455.96") * 2
    assert pv["new_installment"] == "9455.96" and pv["new_count"] < 12
    r = prepay(owner, loan["id"], "40000", "prepay-0002", mode="reduce_term")
    assert r.status_code == 201, r.text  # type: ignore[attr-defined]
    after = detail(owner, loan["id"])
    assert [x["status"] for x in after["schedule"][:2]] == ["paid", "paid"]
    assert after["summary"]["overdue_amount"] == "0.00"
    assert after["installments"] == pv["new_count"] and after["maturity_date"] == pv["new_maturity"]


def test_prepayment_errors(owner: Api) -> None:
    loan = loan_given(owner, "2026-09-04")
    small = owner.get(f"/api/v1/loans/{loan['id']}/prepay", params={"amount": "5000"})
    assert small.status_code == 422 and small.json()["error"]["code"] == "PREPAY_LESS_THAN_DUES"
    big = owner.get(f"/api/v1/loans/{loan['id']}/prepay", params={"amount": "200000"})
    assert big.status_code == 422 and big.json()["error"]["code"] == "PREPAY_USE_SETTLEMENT"
    single = loan_given(owner, "2026-10-30", method="simple_days", frequency="single", term_value=90, term_unit="days")
    r = owner.get(f"/api/v1/loans/{single['id']}/prepay", params={"amount": "1000"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "PREPAY_NOT_FOR_METHOD"


def test_charges_are_paid_first_waived_and_reversed(owner: Api, db) -> None:  # type: ignore[no-untyped-def]
    loan = loan_given(owner, "2026-10-30")
    r = owner.post(f"/api/v1/loans/{loan['id']}/fees", json={"kind": "bounce", "amount": "500", "note": "cheque 000123"})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["summary"]["fees_outstanding"] == "500.00"
    assert D(d["summary"]["total_outstanding"]) == D("113471.53") + D("500")
    paid = pay(owner, loan["id"], "600")
    assert paid.status_code == 201, paid.text
    d = detail(owner, loan["id"])
    assert d["fees"][0]["paid"] == "500.00" and d["fees"][0]["due"] == "0.00"
    assert D(d["schedule"][0]["paid_interest"]) == D("100")  # the rest went to the first installment
    # A legal notice charge, half waived.
    owner.post(f"/api/v1/loans/{loan['id']}/fees", json={"kind": "legal", "amount": "1000"})
    fee_id = detail(owner, loan["id"])["fees"][1]["id"]
    w = owner.post(f"/api/v1/fees/{fee_id}/waive", json={"amount": "400", "reason": "old customer"})
    assert w.status_code == 200 and w.json()["fees"][1]["due"] == "600.00"
    assert owner.post(f"/api/v1/fees/{fee_id}/waive", json={"amount": "700", "reason": "x x"}).status_code == 422
    # Reversing the payment makes the bounce charge due again.
    owner.step_up()
    rev = owner.post(f"/api/v1/payments/{paid.json()['id']}/reverse", json={"reason": "cheque bounced"})
    assert rev.status_code == 200, rev.text
    d = detail(owner, loan["id"])
    assert d["fees"][0]["due"] == "500.00" and d["summary"]["fees_outstanding"] == "1100.00"
    assert ledger.rebuild_item_cache(db, __import__("uuid").UUID(loan["id"]), fix=False) == []
    other = owner.post(f"/api/v1/loans/{loan['id']}/fees", json={"kind": "other", "amount": "10"})
    assert other.status_code == 422


def test_late_fee_waiver(owner: Api) -> None:
    b = make_borrower(owner)
    r = owner.post("/api/v1/loans", json={
        "borrower_id": b["id"], "idempotency_key": "late-fee-loan-01",
        "terms": {"principal": "10000", "rate": "2", "term_value": 6, "disbursal_date": "2026-09-04"},
        "penalty": {"mode": "per_day", "value": "10", "grace_days": 0}})
    assert r.status_code == 201, r.text
    loan = r.json()
    due = D(loan["summary"]["penalty_outstanding"])
    assert due > 0
    too_much = owner.post(f"/api/v1/loans/{loan['id']}/waive-late-fee", json={"amount": str(due + 1), "reason": "kind"})
    assert too_much.status_code == 422
    part = owner.post(f"/api/v1/loans/{loan['id']}/waive-late-fee", json={"amount": "50", "reason": "festival"})
    assert part.status_code == 200 and D(part.json()["summary"]["penalty_outstanding"]) == due - 50
    allw = owner.post(f"/api/v1/loans/{loan['id']}/waive-late-fee", json={"reason": "hospital"})
    assert allw.json()["summary"]["penalty_outstanding"] == "0.00"


def test_closing_early_with_foreclosure_charge_and_rebate_choices(owner: Api) -> None:
    loan = loan_given(owner, "2026-10-30", method="flat")
    base = owner.get(f"/api/v1/loans/{loan['id']}/settlement").json()
    assert base["foreclosure_percent"] == "2.00" and base["rebate"] == "pro_rata"
    assert D(base["foreclosure_charge"]) == (D(base["principal"]) * D("0.02")).quantize(D("0.01"))
    r78 = owner.get(f"/api/v1/loans/{loan['id']}/settlement", params={"rebate": "rule_of_78"}).json()
    none = owner.get(f"/api/v1/loans/{loan['id']}/settlement", params={"rebate": "none"}).json()
    assert D(base["interest"]) < D(r78["interest"]) < D(none["interest"]) == D("24000")
    owner.post(f"/api/v1/loans/{loan['id']}/fees", json={"kind": "seizure", "amount": "1500"})
    waived = owner.get(f"/api/v1/loans/{loan['id']}/settlement",
                       params={"rebate": "rule_of_78", "foreclosure_charge": "0"}).json()
    assert waived["foreclosure_charge"] == "0.00" and waived["charges"] == "1500.00"
    assert D(waived["total"]) == D(r78["total"]) - D(r78["foreclosure_charge"]) + D("1500")
    s = owner.post(f"/api/v1/loans/{loan['id']}/settle", json={
        "expected_total": base["total"], "idempotency_key": "settle-0001"})
    assert s.status_code == 409  # the charge added since then changes the total
    ok_total = owner.get(f"/api/v1/loans/{loan['id']}/settlement").json()["total"]
    s = owner.post(f"/api/v1/loans/{loan['id']}/settle", json={"expected_total": ok_total, "idempotency_key": "settle-0002"})
    assert s.status_code == 200, s.text
    d = detail(owner, loan["id"])
    assert d["stored_status"] == "closed"
    assert {f["kind"]: f["due"] for f in d["fees"]} == {"seizure": "0.00", "foreclosure": "0.00"}
