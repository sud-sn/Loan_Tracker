"""Phase 3: quarterly / half-yearly / yearly, restructure, seizure and sale, release of security
and no-dues certificate, top-up, cheque register, insurance. Invented data only."""

from __future__ import annotations

import io
import uuid
from decimal import Decimal

from pypdf import PdfReader

from app.services import ledger
from tests.conftest import Api, make_borrower, make_loan, pay

D = Decimal
VEHICLE = {"kind": "vehicle", "registration_no": "TN 59 CD 4321", "on_road_price": "200000", "vehicle_type": "car",
           "insurer": "Demo Insurance", "insurance_expiry": "2026-11-20", "originals_held": ["rc_book"]}


def detail(owner: Api, loan_id: str) -> dict:  # type: ignore[type-arg]
    return dict(owner.get(f"/api/v1/loans/{loan_id}").json())


def vehicle_loan(owner: Api, key: str, given: str = "2026-09-04", **extra: object) -> dict:  # type: ignore[type-arg]
    b = make_borrower(owner)
    r = owner.post("/api/v1/loans", json={"borrower_id": b["id"], "idempotency_key": key, "security": [VEHICLE],
                                          "terms": {"principal": "100000", "rate": "2", "term_value": 12,
                                                    "disbursal_date": given}, **extra})
    assert r.status_code == 201, r.text
    return dict(r.json())


def test_quarterly_half_yearly_and_yearly_installments(owner: Api) -> None:
    b = make_borrower(owner)
    q = make_loan(owner, b["id"], frequency="quarterly", method="interest_only", term_value=12, disbursal_date="2026-01-05")
    assert [r["due_date"] for r in q["schedule"]] == ["2026-04-05", "2026-07-05", "2026-10-05", "2027-01-05"]
    assert q["schedule"][0]["interest_part"] == "6000.00"  # 2 % a month x 3 months
    y = make_loan(owner, b["id"], frequency="yearly", term_value=24, disbursal_date="2026-01-05")
    assert len(y["schedule"]) == 2 and y["schedule"][0]["due_date"] == "2027-01-05"
    h = make_loan(owner, b["id"], frequency="half_yearly", method="flat", term_value=12, disbursal_date="2026-01-05")
    assert h["schedule"][0]["interest_part"] == "12000.00"


def test_restructure_with_emi_holiday_and_new_rate(owner: Api, db) -> None:  # type: ignore[no-untyped-def]
    loan = vehicle_loan(owner, "restructure-01")  # due 04/10 (overdue) and 04/11
    body = {"holiday": 2, "extra_installments": 6, "new_rate": "1.5", "reason": "crop failed"}
    pv = owner.post(f"/api/v1/loans/{loan['id']}/restructure/preview", json=body).json()
    assert pv["principal"] == "100000.00" and D(pv["carried_interest"]) > D("4000")  # 2 overdue + 2 skipped
    assert pv["new_count"] == 18 and D(pv["new_installment"]) < D("9455.96") and pv["rate"] == "1.5"
    r = owner.post(f"/api/v1/loans/{loan['id']}/restructure", json=body)
    assert r.status_code == 200, r.text
    d = r.json()
    assert [x["status"] for x in d["schedule"][:12]] == ["rescheduled"] * 12
    assert d["summary"]["overdue_amount"] == "0.00" and d["current_rate"] == "1.5000"
    assert d["reschedules"][0]["kind"] == "restructure" and d["reschedules"][0]["holiday_months"] == 2
    assert d["schedule"][12]["due_date"] > "2026-12-04"  # two installments skipped
    assert ledger.rebuild_item_cache(db, uuid.UUID(loan["id"]), fix=False) == []
    # A part payment afterwards uses the new rate.
    p = owner.get(f"/api/v1/loans/{loan['id']}/prepay", params={"amount": "10000"}).json()
    assert D(p["new_installment"]) < D(d["installment_amount"])


def test_restructure_needs_the_late_fee_settled_first(owner: Api) -> None:
    b = make_borrower(owner)
    loan = owner.post("/api/v1/loans", json={
        "borrower_id": b["id"], "idempotency_key": "restructure-02",
        "terms": {"principal": "10000", "rate": "2", "term_value": 6, "disbursal_date": "2026-09-04"},
        "penalty": {"mode": "per_day", "value": "10"}}).json()
    r = owner.post(f"/api/v1/loans/{loan['id']}/restructure", json={"holiday": 1, "reason": "illness"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "LATE_FEE_DUE_FIRST"


def test_seized_vehicle_sold_for_more_than_owed_closes_and_refunds(owner: Api) -> None:
    loan = vehicle_loan(owner, "seize-01")
    assert owner.post(f"/api/v1/loans/{loan['id']}/sell", json={"sale_price": "1", "idempotency_key": "sell-x-01"}
                      ).status_code == 409
    s = owner.post(f"/api/v1/loans/{loan['id']}/seize", json={"note": "parked at yard", "charge": "2000"})
    assert s.status_code == 200 and s.json()["recovery_status"] == "seized"
    r = owner.post(f"/api/v1/loans/{loan['id']}/sell", json={"sale_price": "150000", "expenses": "3000",
                                                           "idempotency_key": "sell-0001"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["closed"] is True and D(out["refund"]) > 0 and out["shortfall"] == "0.00"
    assert D(out["paid_to_loan"]) + D(out["refund"]) == D("150000")
    d = detail(owner, loan["id"])
    assert d["stored_status"] == "closed" and d["recovery_status"] == "sold"
    assert d["refunds"][0]["amount"] == out["refund"]
    day = owner.get("/api/v1/daybook", params={"on": "2026-11-04"}).json()
    kinds = {e["kind"] for e in day["entries_in"]} | {e["kind"] for e in day["entries_out"]}
    assert {"sale_surplus", "refund"} <= kinds


def test_vehicle_sold_for_less_leaves_a_shortfall(owner: Api) -> None:
    loan = vehicle_loan(owner, "seize-02")
    owner.post(f"/api/v1/loans/{loan['id']}/seize", json={})
    out = owner.post(f"/api/v1/loans/{loan['id']}/sell", json={"sale_price": "40000", "idempotency_key": "sell-0002"}).json()
    assert out["closed"] is False and D(out["shortfall"]) > D("60000")
    d = detail(owner, loan["id"])
    assert d["stored_status"] == "active" and D(d["summary"]["principal_outstanding"]) < D("100000")


def test_release_documents_and_no_dues_certificate(owner: Api) -> None:
    loan = vehicle_loan(owner, "release-01", given="2026-10-30")
    sec = loan["security"][0]["id"]
    assert owner.post(f"/api/v1/securities/{sec}/release", json={"released_to": "Borrower"}).status_code == 409
    assert owner.get(f"/api/v1/loans/{loan['id']}/no-dues.pdf").status_code == 409
    total = owner.get(f"/api/v1/loans/{loan['id']}/settlement", params={"foreclosure_charge": "0"}).json()["total"]
    assert owner.post(f"/api/v1/loans/{loan['id']}/settle", json={
        "expected_total": total, "foreclosure_charge": "0", "idempotency_key": "release-settle"}).status_code == 200
    r = owner.post(f"/api/v1/securities/{sec}/release", json={"released_to": "Borrower in person"})
    assert r.status_code == 200 and r.json()["security"][0]["released_to"] == "Borrower in person"
    for lang, word in (("en", "No-dues certificate"), ("ta", "TN 59 CD 4321")):
        pdf = owner.get(f"/api/v1/loans/{loan['id']}/no-dues.pdf", params={"lang": lang})
        text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
        assert pdf.status_code == 200 and word in text and loan["loan_no"] in text


def test_top_up_closes_the_earlier_loan(owner: Api) -> None:
    old = vehicle_loan(owner, "topup-old-01", given="2026-10-30")
    pv = owner.post("/api/v1/loans/preview", json={"principal": "150000", "rate": "2", "term_value": 24,
                                                   "disbursal_date": "2026-11-04", "topup_of": old["id"]}).json()
    closing = D(pv["topup_closing"])
    assert closing > D("100000") and D(pv["amount_handed_over"]) == D("150000") - closing
    assert pv["security_value"] == "200000.00"  # the vehicle moves to the new loan
    r = owner.post("/api/v1/loans", json={"borrower_id": old["borrower"]["id"], "idempotency_key": "topup-new-01",
                                          "topup_of": old["id"], "terms": {"principal": "150000", "rate": "2",
                                                                           "term_value": 24, "disbursal_date": "2026-11-04"}})
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["topup_of"] == old["loan_no"] and new["security"][0]["registration_no"] == "TN 59 CD 4321"
    assert D(new["amount_handed_over"]) == D("150000") - closing
    assert detail(owner, old["id"])["stored_status"] == "closed"
    other = make_borrower(owner)
    bad = owner.post("/api/v1/loans", json={"borrower_id": other["id"], "idempotency_key": "topup-bad-01",
                                            "topup_of": old["id"], "terms": {"principal": "1000", "rate": "2",
                                                                             "term_value": 2, "disbursal_date": "2026-11-04"}})
    assert bad.status_code == 422


def test_cheques_bounce_adds_the_charge(owner: Api) -> None:
    loan = vehicle_loan(owner, "cheque-01", given="2026-10-30")
    r = owner.post(f"/api/v1/loans/{loan['id']}/cheques", json={"cheque_no": "000123", "bank": "Demo Bank",
                                                              "amount": "9455.96", "cheque_date": "2026-11-30"})
    assert r.status_code == 201, r.text
    ch = r.json()["cheques"][0]
    b = owner.post(f"/api/v1/cheques/{ch['id']}/status", json={"status": "bounced", "version": ch["version"]})
    assert b.status_code == 200, b.text
    d = b.json()
    assert d["cheques"][0]["status"] == "bounced"
    assert d["fees"][0]["kind"] == "bounce" and d["fees"][0]["amount"] == "500.00"
    paid = pay(owner, loan["id"], "500")
    assert paid.status_code == 201 and detail(owner, loan["id"])["fees"][0]["due"] == "0.00"


def test_insurance_due_and_editing_security(owner: Api) -> None:
    loan = vehicle_loan(owner, "insurance-01", given="2026-10-30")
    due = owner.get("/api/v1/insurance/due").json()
    assert any(x["loan_no"] == loan["loan_no"] and x["expired"] is False for x in due)
    sec = loan["security"][0]
    r = owner.patch(f"/api/v1/securities/{sec['id']}", json={"version": sec["version"], "insurance_expiry": "2027-11-20",
                                                              "insurance_policy_no": "POL-2027", "registration_no": "TN59CD9999"})
    assert r.status_code == 200, r.text
    assert r.json()["security"][0]["insurance_policy_no"] == "POL-2027"
    assert not any(x["loan_no"] == loan["loan_no"] for x in owner.get("/api/v1/insurance/due").json())
    hits = owner.get("/api/v1/search", params={"q": "9999"}).json()
    assert any(h.get("loan_no") == loan["loan_no"] for h in hits)
