"""Vehicle and land loans (Phase 1): security and loan-to-value, charges and the amount handed
over, advance EMIs, odd first period, rounded EMI, decimal rates, true cost and search by vehicle
registration. Invented data only."""

from __future__ import annotations

import io
from decimal import Decimal

import pytest
from pypdf import PdfReader
from sqlalchemy import text

from tests.conftest import Api, make_borrower

GIVEN = "2026-11-02"

VEHICLE = {
    "kind": "vehicle", "vehicle_type": "two_wheeler", "vehicle_condition": "new", "registration_no": "TN 59 ab-1234",
    "make_model": "Demo Motors Swift 125", "year": 2026, "chassis_no": "DEMOCHASSIS0001", "engine_no": "DEMOENG0001",
    "on_road_price": "120000", "down_payment": "20000", "insurer": "Demo Insurance", "insurance_policy_no": "POL-1",
    "insurance_expiry": "2027-11-01", "lien_noted_on_rc": True, "originals_held": ["rc_book", "duplicate_key"],
}
LAND = {
    "kind": "land", "survey_no": "123/4B", "patta_no": "567", "extent": "1.20 acres", "village": "Demo Village",
    "taluk": "Demo Taluk", "district": "Madurai", "document_no": "1234/2020", "sub_registrar_office": "Demo SRO",
    "guideline_value": "250000", "market_value": "300000", "ec_checked": True, "ec_date": "2026-10-30",
    "originals_held": ["sale_deed", "patta", "ec"],
}


def vehicle_terms(**kw: object) -> dict[str, object]:
    terms: dict[str, object] = {
        "principal": "100000", "rate": "12", "rate_basis": "year", "method": "flat", "term_value": 36,
        "disbursal_date": GIVEN, "first_due_date": "2026-12-12", "emi_rounding": "10", "advance_installments": 1,
        "broken_period": "first_installment",
    }
    terms.update(kw)
    return terms


CHARGES = [
    {"kind": "processing_fee", "amount": "2000", "treatment": "deducted"},
    {"kind": "insurance", "amount": "3000", "treatment": "added"},
]


def create(api: Api, borrower_id: str, key: str, **body: object) -> object:
    return api.post("/api/v1/loans", json={"borrower_id": borrower_id, "idempotency_key": key, **body})


def test_vehicle_loan_with_down_payment_charges_advance_emi_and_odd_first_period(owner: Api) -> None:
    b = make_borrower(owner)
    p = owner.post("/api/v1/loans/preview", json={**vehicle_terms(), "charges": CHARGES, "security": [VEHICLE]}).json()
    # Loan amount 1,00,000 (price 1,20,000 less 20,000 down) + insurance added = 1,03,000 financed.
    assert p["loan_amount"] == "100000.00" and p["total_principal"] == "103000.00"
    assert p["charges_added"] == "3000.00" and p["charges_deducted"] == "2000.00"
    assert Decimal(p["installment"]) % 10 == 0 and p["unrounded_installment"] is not None
    assert p["advance_installments"] == 1 and p["advance_amount"] == p["installment"]
    assert p["broken_period_days"] == 10 and Decimal(p["broken_period_interest"]) > 0
    assert Decimal(p["first_installment"]) == Decimal(p["installment"]) + Decimal(p["broken_period_interest"])
    handed = Decimal("100000") - Decimal("2000") - Decimal(p["advance_amount"])
    assert Decimal(p["amount_handed_over"]) == handed
    assert Decimal(p["true_cost_yearly"]) > Decimal("21")  # 12 % flat is ~21 % reducing, charges add more
    # Loan-to-value: 1,03,000 against a 1,20,000 vehicle = 85.83 %, above the 75 % default.
    assert p["security_value"] == "120000.00" and p["ltv_percent"] == "85.83"
    assert p["ltv_maximum"] == "75.00" and p["ltv_above_maximum"] is True

    body = {"terms": vehicle_terms(), "charges": CHARGES, "security": [VEHICLE]}
    refused = create(owner, b["id"], "vehicle-loan-0001", **body)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "LTV_ABOVE_MAXIMUM"  # type: ignore[attr-defined]
    r = create(owner, b["id"], "vehicle-loan-0002", acknowledge_ltv_warning=True, **body)
    assert r.status_code == 201, r.text  # type: ignore[attr-defined]
    loan = r.json()  # type: ignore[attr-defined]
    assert loan["principal"] == "103000.00" and loan["amount_handed_over"] == f"{handed:.2f}"
    assert loan["security_kind"] == "vehicle" and loan["ltv_percent"] == "85.83"
    assert loan["emi_rounding"] == "10.00" and loan["advance_installments"] == 1
    assert loan["broken_period"] == "first_installment" and loan["broken_period_days"] == 10
    assert Decimal(loan["true_cost_monthly"]) > Decimal("1.77")
    assert {(c["kind"], c["treatment"], c["amount"]) for c in loan["charges"]} == {
        ("processing_fee", "deducted", "2000.00"), ("insurance", "added", "3000.00")}
    sec = loan["security"][0]
    assert sec["registration_no"] == "TN 59 ab-1234" and sec["value"] == "120000.00" and sec["down_payment"] == "20000.00"
    assert sec["originals_held"] == ["rc_book", "duplicate_key"] and sec["lien_noted_on_rc"] is True
    # The advance EMI is a payment on the day the loan was given; the first row is paid.
    assert len(loan["payments"]) == 1
    assert loan["payments"][0]["amount"] == p["advance_amount"] and loan["payments"][0]["paid_on"] == GIVEN
    assert loan["schedule"][0]["status"] == "paid" and loan["schedule"][0]["due_date"] == GIVEN
    assert loan["schedule"][1]["due_date"] == "2026-12-12"

    # Daily log: loan out (financed), charges and the advance EMI in; the net is what was handed over.
    day = owner.get("/api/v1/daybook", params={"on": GIVEN}).json()
    assert Decimal(day["money_out"]) == Decimal("103000")
    assert Decimal(day["money_in"]) == Decimal("2000") + Decimal("3000") + Decimal(p["advance_amount"])
    assert Decimal(day["money_out"]) - Decimal(day["money_in"]) == handed
    charge_lines = [e for e in day["entries_in"] if e["kind"] == "charge"]
    assert {e["category_en"] for e in charge_lines} == {"Processing fee", "Insurance"}
    assert {e["category_ta"] for e in charge_lines} == {"செயலாக்கக் கட்டணம்", "காப்பீடு"}
    owner.step_up()
    csv = owner.get("/api/v1/daybook/export", params={"start": GIVEN, "end": GIVEN, "fmt": "csv", "lang": "en"})
    assert csv.status_code == 200 and "Processing fee" in csv.text and "Insurance" in csv.text

    # The printed loan summary shows the charges, the amount handed over and the vehicle.
    for lang, words in (("en", ("Processing fee", "Handed over", "TN 59 ab-1234", "Vehicle")),
                        ("ta", ("காப்பீடு", "TN 59 ab-1234"))):  # words without pre-base vowels extract cleanly
        r = owner.get(f"/api/v1/loans/{loan['id']}/summary.pdf", params={"lang": lang})
        pdf_text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(r.content)).pages)
        for word in words:
            assert word in pdf_text, (lang, word)


def test_land_loan_interest_only_at_a_decimal_rate_with_extra_days_collected_up_front(owner: Api) -> None:
    b = make_borrower(owner)
    terms = {"principal": "100000", "rate": "2.45", "method": "interest_only", "term_value": 12,
             "disbursal_date": GIVEN, "first_due_date": "2026-12-12", "broken_period": "upfront"}
    r = create(owner, b["id"], "land-loan-0001", terms=terms, security=[LAND])
    assert r.status_code == 201, r.text  # type: ignore[attr-defined]
    loan = r.json()  # type: ignore[attr-defined]
    assert Decimal(loan["rate"]) == Decimal("2.45") and loan["security_kind"] == "land"
    assert loan["ltv_percent"] == "33.33"  # 1,00,000 against a 3,00,000 market value: under 50 %
    assert {s["interest_part"] for s in loan["schedule"][:-1]} == {"2450.00"}
    odd = [c for c in loan["charges"] if c["kind"] == "odd_period_interest"]
    assert odd == [{"kind": "odd_period_interest", "label": None, "amount": "816.67", "treatment": "deducted"}]
    assert loan["amount_handed_over"] == "99183.33"  # 10 extra days at 2.45 % / 30 collected up front
    land = loan["security"][0]
    assert land["survey_no"] == "123/4B" and land["market_value"] == "300000.00" and land["value"] == "300000.00"


def test_search_finds_a_loan_by_vehicle_registration(owner: Api) -> None:
    b = make_borrower(owner)
    r = create(owner, b["id"], "vehicle-search-01", terms=vehicle_terms(advance_installments=0),
               security=[{**VEHICLE, "on_road_price": "200000"}])
    assert r.status_code == 201, r.text  # type: ignore[attr-defined]
    loan_no = r.json()["loan_no"]  # type: ignore[attr-defined]
    for q in ("TN59AB1234", "tn 59 ab 1234", "59AB12", "1234"):
        hits = owner.get("/api/v1/search", params={"q": q}).json()
        assert any(h.get("loan_no") == loan_no and h["matched"] == "vehicle" for h in hits), q


def test_charges_and_new_terms_are_locked_in_the_database(owner: Api, db) -> None:  # type: ignore[no-untyped-def]
    b = make_borrower(owner)
    r = create(owner, b["id"], "locked-terms-01", terms=vehicle_terms(), charges=CHARGES,
               security=[{**VEHICLE, "value": "200000"}])
    assert r.status_code == 201, r.text  # type: ignore[attr-defined]
    for sql in ("UPDATE loan_charge SET amount = 1", "DELETE FROM loan_charge",
                "UPDATE loan SET amount_handed_over = 1", "UPDATE loan SET emi_rounding = 1",
                "UPDATE loan SET advance_installments = 0"):
        with pytest.raises(Exception, match="locked|append-only"):
            db.execute(text(sql))
        db.rollback()


@pytest.mark.parametrize(("change", "code"), [
    ({"charges": [{"kind": "processing_fee", "amount": "99000"}], "terms": vehicle_terms(advance_installments=1)},
     "HANDED_OVER_NOT_POSITIVE"),
    ({"terms": vehicle_terms(method="interest_only", advance_installments=1)}, "ADVANCE_NOT_FOR_METHOD"),
    ({"terms": vehicle_terms(emi_rounding="7")}, "ROUNDING_INVALID"),
])
def test_invalid_vehicle_loans_are_refused(owner: Api, change: dict, code: str) -> None:  # type: ignore[type-arg]
    b = make_borrower(owner)
    body = {"terms": vehicle_terms(), **change}
    r = owner.post("/api/v1/loans/preview", json={**body["terms"], "charges": body.get("charges", [])})
    assert r.status_code == 422 and r.json()["error"]["code"] == code, r.text
    assert create(owner, b["id"], f"bad-{code[:20]}", **body).status_code == 422  # type: ignore[attr-defined]


def test_security_details_are_checked(owner: Api) -> None:
    bad = [
        {**VEHICLE, "down_payment": "120000"},  # down payment as large as the price
        {**VEHICLE, "vehicle_type": "plane"},
        {**LAND, "originals_held": ["crown"]},
    ]
    for sec in bad:
        r = owner.post("/api/v1/loans/preview", json={**vehicle_terms(), "security": [sec]})
        assert r.status_code == 422, sec
    other = owner.post("/api/v1/loans/preview", json={**vehicle_terms(), "charges": [{"kind": "other", "amount": "10"}]})
    assert other.status_code == 422


def test_new_loan_defaults_in_settings(owner: Api, staff: Api) -> None:
    s = owner.get("/api/v1/settings").json()
    assert (s["ltv_max_vehicle"], s["ltv_max_land"], s["emi_rounding_default"]) == ("75.00", "50.00", "10.00")
    assert s["broken_period_default"] == "first_installment" and s["advance_installments_default"] == 0
    assert s["processing_fee_percent"] == "0.00" and s["document_charges_default"] == "0.00"
    r = owner.put("/api/v1/settings", json={"version": s["version"], "ltv_max_vehicle": "80", "emi_rounding_default": "100",
                                            "processing_fee_percent": "1.5", "document_charges_default": "500"})
    assert r.status_code == 200, r.text
    assert r.json()["emi_rounding_default"] == "100.00" and r.json()["document_charges_default"] == "500.00"
    assert owner.put("/api/v1/settings", json={"version": r.json()["version"], "emi_rounding_default": "7"}).status_code == 422
    seen = staff.get("/api/v1/settings").json()
    assert Decimal(seen["ltv_max_vehicle"]) == 80 and Decimal(seen["processing_fee_percent"]) == Decimal("1.5")
    assert "licence_no" not in seen
