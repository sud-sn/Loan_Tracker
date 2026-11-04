"""Uploads, the daily log, notebook import and Tamil PDFs (acceptance checks 8, 9, 15, 16, 19)."""

from __future__ import annotations

import io
import shutil
import subprocess
import time
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook
from pypdf import PdfReader

from app.services.scanner import EICAR
from tests.conftest import TODAY, Api, make_borrower, make_loan, pay

MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def _upload(api: Api, owner_id: str, name: str, data: bytes, doc_type: str = "other", owner_type: str = "borrower"):  # type: ignore[no-untyped-def]
    return api.post("/api/v1/documents", data={"owner_type": owner_type, "owner_id": owner_id, "doc_type": doc_type},
                    files={"file": (name, data, "application/octet-stream")})


def test_upload_checks_content_not_extension(owner: Api) -> None:
    b = make_borrower(owner)
    exe = b"MZ\x90\x00" + b"\x00" * 100  # a Windows executable renamed to .pdf
    r = _upload(owner, b["id"], "agreement.pdf", exe)
    assert r.status_code == 415 and r.json()["error"]["code"] == "FILE_TYPE_NOT_ALLOWED"
    r = _upload(owner, b["id"], "eicar.pdf", EICAR)
    assert r.status_code == 415
    r = _upload(owner, b["id"], "eicar.pdf", MINIMAL_PDF + EICAR)  # a real PDF carrying the test virus
    assert r.status_code == 422 and r.json()["error"]["code"] == "FILE_INFECTED"
    ok = _upload(owner, b["id"], "proof.pdf", MINIMAL_PDF, "address_proof")
    assert ok.status_code == 201 and ok.json()["mime"] == "application/pdf"


def test_upload_limits_and_soft_delete(owner: Api) -> None:
    s = owner.get("/api/v1/settings").json()
    owner.put("/api/v1/settings", json={"version": s["version"], "max_files_per_owner": 2, "max_upload_mb": 1})
    b = make_borrower(owner)
    assert _upload(owner, b["id"], "a.pdf", MINIMAL_PDF).status_code == 201
    assert _upload(owner, b["id"], "big.pdf", MINIMAL_PDF + b"0" * (1024 * 1024)).status_code == 413
    doc = _upload(owner, b["id"], "b.pdf", MINIMAL_PDF).json()
    assert _upload(owner, b["id"], "c.pdf", MINIMAL_PDF).json()["error"]["code"] == "TOO_MANY_FILES"
    assert owner.delete(f"/api/v1/documents/{doc['id']}").status_code == 200
    assert _upload(owner, b["id"], "c.pdf", MINIMAL_PDF).status_code == 201


def test_daybook_balance_in_out_and_reconciliation(owner: Api, db) -> None:  # type: ignore[no-untyped-def]
    s = owner.get("/api/v1/settings").json()
    owner.put("/api/v1/settings", json={"version": s["version"], "balance_start_date": "2026-11-01",
                                        "opening_balance": "50000.00"})
    cats = owner.get("/api/v1/categories").json()
    food = next(c for c in cats if c["name_en"] == "Food")
    other_in = next(c for c in cats if c["kind"] == "income")
    b = make_borrower(owner)
    old = make_loan(owner, b["id"], disbursal_date="2026-10-01", principal="20000", term_value=4)  # before start
    new = make_loan(owner, b["id"], disbursal_date="2026-11-02", principal="10000", term_value=2)
    pay(owner, old["id"], "5000", paid_on="2026-11-02", mode="upi")
    owner.post("/api/v1/cash-entries", json={"direction": "out", "category_id": food["id"], "amount": "250",
                                             "entry_date": "2026-11-02"})
    owner.post("/api/v1/cash-entries", json={"direction": "in", "category_id": other_in["id"], "amount": "1000",
                                             "entry_date": "2026-11-03"})
    d = owner.get("/api/v1/daybook", params={"on": "2026-11-02"}).json()
    assert d["opening_balance"] == "50000.00"
    assert d["money_in"] == "5000.00" and d["money_out"] == "10250.00"
    assert d["closing_balance"] == "44750.00"
    assert Decimal(d["closing_balance"]) == Decimal(d["opening_balance"]) + Decimal(d["money_in"]) - Decimal(d["money_out"])
    assert {e["source_type"] for e in d["entries_in"]} == {"payment"}
    assert d["entries_in"][0]["interest"] == "400.00"  # split shown on the home page
    assert {e["kind"] for e in d["entries_out"]} == {"loan", "expense"}
    assert d["by_mode"]["upi"]["in"] == "5000.00"
    next_day = owner.get("/api/v1/daybook", params={"on": "2026-11-03"}).json()
    assert next_day["opening_balance"] == d["closing_balance"]
    assert owner.get("/api/v1/daybook", params={"on": "2026-10-01"}).json()["tracked"] is False
    from datetime import date

    from app.services import daybook

    r = daybook.reconcile(db, date(2026, 1, 1), date(2026, 12, 31))
    assert r["view_in"] == r["source_in"] and r["view_out"] == r["source_out"]
    assert new["loan_no"].startswith("LN-2026-")


def test_expense_is_quick_and_shows_at_once(owner: Api) -> None:
    food = next(c for c in owner.get("/api/v1/categories").json() if c["name_en"] == "Food")
    start = time.perf_counter()
    r = owner.post("/api/v1/cash-entries", json={"direction": "out", "category_id": food["id"], "amount": "120"})
    assert r.status_code == 201 and time.perf_counter() - start < 0.5
    d = owner.get("/api/v1/daybook").json()
    assert d["entries_out"][0]["amount"] == "120.00" and d["entries_out"][0]["category_ta"] == "உணவு"
    e = r.json()
    owner.patch(f"/api/v1/cash-entries/{e['id']}", json={"version": e["version"], "amount": "130"})
    owner.delete(f"/api/v1/cash-entries/{e['id']}")
    history = owner.get(f"/api/v1/cash-entries/{e['id']}/history").json()
    assert [h["action"] for h in history] == ["create", "update", "delete"]


def test_reversal_shows_as_negative_money_in_on_its_day(owner: Api) -> None:
    b = make_borrower(owner)
    loan = make_loan(owner, b["id"], disbursal_date="2026-10-01")
    p = pay(owner, loan["id"], "3000", paid_on="2026-11-01").json()
    owner.step_up()
    owner.post(f"/api/v1/payments/{p['id']}/reverse", json={"reason": "wrong loan"})
    assert owner.get("/api/v1/daybook", params={"on": "2026-11-01"}).json()["money_in"] == "3000.00"
    assert owner.get("/api/v1/daybook").json()["money_in"] == "-3000.00"


def _workbook(rows: int) -> bytes:
    from app.services import importer

    wb = load_workbook(io.BytesIO(importer.template()))
    loans, pays = wb["Loans"], wb["Payments"]
    loans.delete_rows(2)
    pays.delete_rows(2)
    for i in range(rows):
        loans.append([f"P{i}", f"Notebook Person {i}", "", "", f"8{100000000 + i:09d}", "", f"{i} Main Rd", "ta",
                      "10000", "2", "month", "flat" if i % 2 else "reducing", "monthly", "10", "months", "",
                      "01/03/2026", "", "cash", f"page {i}"])
        pays.append([f"P{i}", "01/04/2026", "1200", "cash", "", ""])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_import_100_notebook_loans_with_preview_and_errors(owner: Api) -> None:
    data = _workbook(100)
    r = owner.post("/api/v1/import/preview", files={"file": ("notebook.xlsx", data)})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["errors"] == [] and p["loans"] == 100 and p["payments"] == 100
    assert Decimal(p["total_principal"]) == Decimal("1000000.00")
    assert Decimal(p["total_paid"]) == Decimal("120000.00")
    c = owner.post("/api/v1/import/commit", files={"file": ("notebook.xlsx", data)})
    assert c.status_code == 200, c.text
    dash = owner.get("/api/v1/dashboard").json()
    assert dash["active_loans"] == 100
    assert Decimal(dash["total_to_receive"]) == Decimal(p["total_outstanding"])
    again = owner.post("/api/v1/import/commit", files={"file": ("notebook.xlsx", data)})
    assert again.json()["error"]["code"] == "IMPORT_ALREADY_DONE"
    # The imported borrowers have no Aadhaar yet: flagged incomplete, new loans blocked until it is added.
    first = owner.get("/api/v1/borrowers", params={"sort": "code"}).json()["items"][0]
    assert first["profile_incomplete"] is True


def test_import_reports_errors_row_by_row(owner: Api) -> None:
    from app.services import importer

    wb = load_workbook(io.BytesIO(importer.template()))
    ws = wb["Loans"]
    ws.append(["P2", "No Phone", "", "", "12345", "", "addr", "ta", "abc", "2", "month", "reducing", "monthly", "12",
               "months", "", "01/01/2026", "", "cash", ""])
    ws.append(["P3", "", "", "", "9876512345", "", "addr", "ta", "1000", "2", "month", "reducing", "monthly", "12",
               "months", "", "01/01/2030", "", "cash", ""])
    wb["Payments"].append(["NOPE", "01/02/2026", "100", "cash", "", ""])
    buf = io.BytesIO()
    wb.save(buf)
    p = owner.post("/api/v1/import/preview", files={"file": ("bad.xlsx", buf.getvalue())}).json()
    codes = {(e["sheet"], e["row"], e["code"]) for e in p["errors"]}
    assert ("Loans", 3, "PHONE_INVALID") in codes
    assert ("Loans", 3, "TERMS_INVALID") in codes
    assert ("Loans", 4, "NAME_REQUIRED") in codes
    assert ("Loans", 4, "DATE_IN_FUTURE") in codes
    assert ("Payments", 3, "REF_NOT_FOUND") in codes  # row 2 is the template's example payment
    assert owner.post("/api/v1/import/commit", files={"file": ("bad.xlsx", buf.getvalue())}).status_code == 422


@pytest.mark.parametrize("lang", ["ta", "en"])
def test_receipt_pdf_renders_in_both_languages(owner: Api, lang: str, tmp_path: Path) -> None:
    b = make_borrower(owner, name_en="Murugan", name_ta="முருகன்", preferred_language=lang)
    loan = make_loan(owner, b["id"])
    p = pay(owner, loan["id"], "9455.96", paid_on="2026-02-05").json()
    r = owner.get(f"/api/v1/payments/{p['id']}/receipt.pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    reader = PdfReader(io.BytesIO(r.content))
    assert len(reader.pages) == 1  # a receipt fits on one A5 page
    page_text = reader.pages[0].extract_text()
    fonts = {str(f) for page in reader.pages for f in page["/Resources"]["/Font"].values()}
    fonts_desc = " ".join(str(reader.get_object(f)["/BaseFont"]) for page in reader.pages
                          for f in page["/Resources"]["/Font"].values())
    assert "RCT-2026-000001" in page_text and "9,455.96" in page_text
    if lang == "ta":
        # Shaped Tamil survives extraction only if glyphs map back to the right characters. Words with
        # vowel signs drawn before the consonant (ெ ே ை) come back reordered from any PDF text
        # extractor, so the check uses words without them; the rendering itself is checked below.
        for word in ("ரசீது", "முருகன்", "வட்டி", "அசல்", "ரூபாய்"[:2]):
            assert word in page_text, word
        assert "NotoSansTamil" in fonts_desc.replace("-", "")
    else:
        assert "Payment receipt" in page_text and "Nine thousand four hundred fifty-five rupees" in page_text
    assert fonts
    if shutil.which("pdftoppm"):
        out = tmp_path / "page"
        subprocess.run(["pdftoppm", "-r", "50", "-png", "-f", "1", "-l", "1", "-", str(out)], input=r.content,
                       check=True)
        image = next(tmp_path.glob("page*.png"))
        assert image.stat().st_size > 5000  # not a blank page


def test_loan_summary_and_statement_pdfs(owner: Api) -> None:
    b = make_borrower(owner, name_ta="செல்வி")
    loan = make_loan(owner, b["id"], method="fixed_amount", fixed_installment="10000", term_value=None)
    for lang in ("ta", "en"):
        r = owner.get(f"/api/v1/loans/{loan['id']}/summary.pdf", params={"lang": lang})
        text = PdfReader(io.BytesIO(r.content)).pages[0].extract_text()
        assert ("கடன் சுருக்கம்" if lang == "ta" else "Loan summary") in text
        assert "₹10,000.00" in text and "LN-2026-000001" in text
        if lang == "en":
            assert "Fixed amount every installment" in text
    r = owner.get(f"/api/v1/borrowers/{b['id']}/statement.pdf", params={"lang": "ta"})
    statement_text = PdfReader(io.BytesIO(r.content)).pages[0].extract_text()
    assert "தயாரித்தது" in statement_text and b["code"] in statement_text


def test_reports_and_exports(owner: Api) -> None:
    b = make_borrower(owner)
    loan = make_loan(owner, b["id"], disbursal_date=(TODAY - timedelta(days=70)).isoformat())
    pay(owner, loan["id"], "9455.96")
    coll = owner.get("/api/v1/reports/collections", params={"start": "2026-11-01", "end": "2026-11-30"}).json()
    assert coll[0]["interest"] == "2000.00" and coll[0]["principal"] == "7455.96"
    assert owner.get("/api/v1/reports/collections/export", params={"fmt": "csv"}).status_code == 403
    owner.step_up()
    csv_body = owner.get("/api/v1/reports/outstanding/export", params={"fmt": "csv", "lang": "ta"}).content.decode()
    assert "வாடிக்கையாளர்" in csv_body and b["code"] in csv_body
    pdf_body = owner.get("/api/v1/reports/ageing/export", params={"fmt": "pdf"}).content
    assert pdf_body.startswith(b"%PDF")
    d = owner.get("/api/v1/dashboard").json()
    assert d["interest_this_month"] == "2000.00" and d["active_loans"] == 1
