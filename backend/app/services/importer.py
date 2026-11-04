"""One-time notebook import (PRD section 15): spreadsheet template, preview, row-by-row errors.

The workbook has a ``Loans`` sheet (one row per loan, borrower details repeated) and a
``Payments`` sheet (earlier payments with their real dates, linked by the ``ref`` column). The
preview builds every schedule and replays every payment with the real engine, so the totals it
shows are exactly what will be saved. Commit runs the whole file in one transaction and refuses
a file that was already imported (by SHA-256).
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import select

from app.core import clock
from app.core.errors import AppError
from app.core.text import nfc, normalize_aadhaar, normalize_phone, search_key
from app.deps import Ctx
from app.engine import EngineError, build_schedule
from app.engine.allocation import OpenItem, allocate
from app.engine.money import ZERO
from app.models import Borrower, ImportBatch
from app.repositories import counters
from app.schemas.loans import LoanCreateIn, PaymentIn, TermsIn
from app.security import crypto
from app.services import audit, loans, payments

LOAN_COLUMNS = [
    "ref", "name_en", "name_ta", "relation_name", "phone", "aadhaar", "address", "preferred_language",
    "principal", "rate", "rate_basis", "method", "frequency", "term_value", "term_unit", "fixed_installment",
    "disbursal_date", "first_due_date", "disbursal_mode", "notes",
]
PAYMENT_COLUMNS = ["ref", "paid_on", "amount", "mode", "reference", "note"]
REQUIRED_LOAN = ["ref", "phone", "address", "principal", "rate", "disbursal_date"]
EXAMPLE_LOAN = ["P12", "Murugan K", "முருகன் க", "Kandasamy", "9876543210", "", "12, Gandhi St, Madurai", "ta",
                "100000", "2", "month", "reducing", "monthly", "12", "months", "", "05/01/2026", "", "cash",
                "notebook page 12"]
EXAMPLE_PAYMENT = ["P12", "05/02/2026", "9455.96", "cash", "", ""]
INSTRUCTIONS = [
    ("en", "One row per loan on the Loans sheet. Repeat the borrower details for each of their loans; the same phone "
           "number means the same borrower."),
    ("en", "Dates as DD/MM/YYYY. Amounts in rupees without commas. rate_basis is month or year."),
    ("en", "method: reducing, flat, interest_only, simple_days, fixed_amount (fill fixed_installment), custom."),
    ("en", "Payments sheet: earlier payments with their real dates. ref links a payment to its loan."),
    ("ta", "Loans தாளில் ஒவ்வொரு கடனுக்கும் ஒரு வரி. ஒரே போன் எண் என்றால் ஒரே நபர்."),
    ("ta", "தேதி DD/MM/YYYY வடிவில். தொகை ரூபாயில், காற்புள்ளி இல்லாமல்."),
    ("ta", "Payments தாளில் முன்பு கட்டிய தொகைகளை உண்மையான தேதியுடன் எழுதுங்கள். ref மூலம் கடனுடன் இணைகிறது."),
]


@dataclass
class RowError:
    sheet: str
    row: int
    field: str
    code: str


@dataclass
class ParsedLoan:
    row: int
    ref: str
    borrower: dict[str, Any]
    terms: TermsIn
    disbursal_mode: str
    notes: str | None
    payments: list[tuple[int, PaymentIn]] = field(default_factory=list)
    total_payable: Decimal = ZERO
    paid: Decimal = ZERO


@dataclass
class Parsed:
    loans: list[ParsedLoan]
    errors: list[RowError]
    sha256: str


def template() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Loans"
    ws.append(LOAN_COLUMNS)
    ws.append(EXAMPLE_LOAN)
    pay = wb.create_sheet("Payments")
    pay.append(PAYMENT_COLUMNS)
    pay.append(EXAMPLE_PAYMENT)
    info = wb.create_sheet("Instructions")
    for lang, line in INSTRUCTIONS:
        info.append([lang, line])
    for sheet in (ws, pay):
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="DCEBE8")
        for col in sheet.columns:
            sheet.column_dimensions[col[0].column_letter].width = 16
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, float):
        return f"{Decimal(str(value))}"
    return str(value).strip()


def _rows(data: bytes, filename: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    if filename.lower().endswith(".csv"):
        text = data.decode("utf-8-sig")
        return [{k.strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(io.StringIO(text))], []
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - any parse failure is a bad file
        raise AppError("IMPORT_FILE_UNREADABLE", 422) from exc

    def sheet(name: str) -> list[dict[str, str]]:
        if name not in wb.sheetnames:
            return []
        values = list(wb[name].iter_rows(values_only=True))
        if not values:
            return []
        header = [_cell(h) for h in values[0]]
        return [dict(zip(header, (_cell(v) for v in row), strict=False)) for row in values[1:]
                if any(v not in (None, "") for v in row)]

    return sheet("Loans"), sheet("Payments")


def _date(value: str) -> date:
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", value)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return date.fromisoformat(value)


def _money(value: str) -> Decimal:
    d = Decimal(value.replace(",", "").replace("₹", "").strip())
    if d != d.quantize(Decimal("0.01")):
        raise InvalidOperation
    return d.quantize(Decimal("0.01"))


def parse(data: bytes, filename: str) -> Parsed:
    loan_rows, payment_rows = _rows(data, filename)
    errors: list[RowError] = []
    parsed: list[ParsedLoan] = []
    by_ref: dict[str, ParsedLoan] = {}
    if not loan_rows:
        errors.append(RowError("Loans", 1, "", "IMPORT_NO_ROWS"))
    today = clock.today()
    for i, r in enumerate(loan_rows, start=2):
        row_errors: list[RowError] = []

        def err(field_name: str, code: str, row: int = i, bucket: list[RowError] = row_errors) -> None:
            bucket.append(RowError("Loans", row, field_name, code))

        for name in REQUIRED_LOAN:
            if not r.get(name):
                err(name, "REQUIRED")
        if not (r.get("name_en") or r.get("name_ta")):
            err("name_en", "NAME_REQUIRED")
        ref = r.get("ref", "")
        if ref in by_ref:
            err("ref", "DUPLICATE_REF")
        phone = aadhaar = None
        try:
            phone = normalize_phone(r.get("phone"))
        except ValueError:
            err("phone", "PHONE_INVALID")
        if r.get("aadhaar"):
            try:
                aadhaar = normalize_aadhaar(r["aadhaar"])
            except ValueError as exc:
                err("aadhaar", str(exc))
        terms = None
        try:
            disbursal = _date(r.get("disbursal_date", ""))
            if disbursal > today:
                err("disbursal_date", "DATE_IN_FUTURE")
            first_due = _date(r["first_due_date"]) if r.get("first_due_date") else None
            method = r.get("method") or "reducing"
            frequency = r.get("frequency") or ("single" if method == "simple_days" else "monthly")
            terms = TermsIn(
                principal=_money(r.get("principal", "")), rate=Decimal(r.get("rate") or "0"),
                rate_basis=r.get("rate_basis") or "month", method=method, frequency=frequency,
                term_value=int(r["term_value"]) if r.get("term_value") else None,
                term_unit=r.get("term_unit") or ("days" if method == "simple_days" else "months"),
                fixed_installment=_money(r["fixed_installment"]) if r.get("fixed_installment") else None,
                disbursal_date=disbursal, first_due_date=first_due,
            )
            schedule = build_schedule(loans.to_terms(terms))
        except EngineError as exc:
            err("terms", exc.code)
        except (ValueError, InvalidOperation, KeyError):
            err("terms", "TERMS_INVALID")
        mode = r.get("disbursal_mode") or "cash"
        if mode not in ("cash", "upi", "bank", "cheque", "other"):
            err("disbursal_mode", "MODE_INVALID")
        errors += row_errors
        if not row_errors and terms is not None:
            loan = ParsedLoan(
                row=i, ref=ref,
                borrower={"name_en": nfc(r.get("name_en")), "name_ta": nfc(r.get("name_ta")),
                          "relation_name": nfc(r.get("relation_name")), "phone": phone, "aadhaar": aadhaar,
                          "address": nfc(r.get("address")),
                          "preferred_language": r["preferred_language"] if r.get("preferred_language") in ("en", "ta")
                          else "ta"},
                terms=terms, disbursal_mode=mode, notes=nfc(r.get("notes")), total_payable=schedule.total_payable,
            )
            parsed.append(loan)
            by_ref[ref] = loan
            loan.schedule = schedule  # type: ignore[attr-defined]

    for j, r in enumerate(payment_rows, start=2):
        target = by_ref.get(r.get("ref", ""))
        if target is None:
            errors.append(RowError("Payments", j, "ref", "REF_NOT_FOUND"))
            continue
        try:
            paid_on = _date(r.get("paid_on", ""))
            amount = _money(r.get("amount", ""))
            mode = r.get("mode") or "cash"
            if amount <= 0:
                raise InvalidOperation
            if paid_on > today:
                errors.append(RowError("Payments", j, "paid_on", "DATE_IN_FUTURE"))
                continue
            if paid_on < target.terms.disbursal_date:
                errors.append(RowError("Payments", j, "paid_on", "DATE_BEFORE_DISBURSAL"))
                continue
            target.payments.append((j, PaymentIn(amount=amount, paid_on=paid_on, mode=mode,
                                               reference=r.get("reference") or None, note=r.get("note") or None,
                                               idempotency_key=f"import-pay-{j:06d}-placeholder")))
        except (ValueError, InvalidOperation):
            errors.append(RowError("Payments", j, "amount", "PAYMENT_INVALID"))

    # Replay payments oldest first with the real allocation rules.
    for loan in parsed:
        loan.payments.sort(key=lambda p: (p[1].paid_on or today, p[0]))
        rows = loan.schedule.rows  # type: ignore[attr-defined]
        due = {r.seq: [ZERO, r.interest_part, r.principal_part] for r in rows}
        for j, pay in loan.payments:
            items = [OpenItem(str(seq), seq, v[0], v[1], v[2]) for seq, v in due.items()]
            try:
                for ln in allocate(pay.amount, items):
                    due[int(ln.item_id)][1] -= ln.interest_part
                    due[int(ln.item_id)][2] -= ln.principal_part
                loan.paid += pay.amount
            except EngineError as exc:
                errors.append(RowError("Payments", j, "amount", exc.code))
    return Parsed(parsed, errors, crypto.sha256_hex(data))


def summary(p: Parsed) -> dict[str, Any]:
    return {
        "loans": len(p.loans),
        "borrowers": len({ln.borrower["phone"] for ln in p.loans}),
        "payments": sum(len(ln.payments) for ln in p.loans),
        "total_principal": sum((ln.terms.principal for ln in p.loans), ZERO),
        "total_payable": sum((ln.total_payable for ln in p.loans), ZERO),
        "total_paid": sum((ln.paid for ln in p.loans), ZERO),
        "total_outstanding": sum((ln.total_payable - ln.paid for ln in p.loans), ZERO),
        "missing_aadhaar": sum(1 for ln in p.loans if not ln.borrower["aadhaar"]),
        "errors": [e.__dict__ for e in p.errors],
        "sha256": p.sha256,
        "rows": [
            {"row": ln.row, "ref": ln.ref, "name_en": ln.borrower["name_en"], "name_ta": ln.borrower["name_ta"],
             "phone": ln.borrower["phone"], "principal": ln.terms.principal, "method": ln.terms.method,
             "disbursal_date": ln.terms.disbursal_date, "payments": len(ln.payments), "paid": ln.paid,
             "outstanding": ln.total_payable - ln.paid}
            for ln in p.loans
        ],
    }


def commit(ctx: Ctx, data: bytes, filename: str) -> dict[str, Any]:
    p = parse(data, filename)
    if p.errors:
        raise AppError("IMPORT_HAS_ERRORS", 422, count=len(p.errors))
    db = ctx.db
    if db.scalars(select(ImportBatch).where(ImportBatch.sha256 == p.sha256)).first():
        raise AppError("IMPORT_ALREADY_DONE", 409)
    batch = ImportBatch(created_by=ctx.user.id, filename=filename[:255], sha256=p.sha256,
                        summary={k: str(v) for k, v in summary(p).items() if k not in ("rows", "errors")})
    db.add(batch)
    db.flush()
    borrowers: dict[str, Borrower] = {}
    for ln in p.loans:
        info = ln.borrower
        b = borrowers.get(info["phone"]) or db.scalars(
            select(Borrower).where(Borrower.phone == info["phone"], Borrower.deleted_at.is_(None))
        ).first()
        if b is None:
            b = Borrower(code=counters.next_borrower_code(db), name_en=info["name_en"], name_ta=info["name_ta"],
                         relation_name=info["relation_name"], phone=info["phone"], address=info["address"],
                         preferred_language=info["preferred_language"], created_by=ctx.user.id,
                         import_batch_id=batch.id, name_latin=search_key(info["name_en"], info["name_ta"]))
            if info["aadhaar"]:
                b.aadhaar_encrypted = crypto.encrypt(info["aadhaar"], crypto.AADHAAR)
                b.aadhaar_hash = crypto.aadhaar_hmac(info["aadhaar"])
                b.aadhaar_last4 = info["aadhaar"][-4:]
            db.add(b)
            db.flush()
        borrowers[info["phone"]] = b
        loan = loans.create(
            ctx,
            LoanCreateIn(borrower_id=b.id, terms=ln.terms, disbursal_mode=ln.disbursal_mode, notes=ln.notes,
                         acknowledge_rate_warning=True, idempotency_key=f"import-{p.sha256[:16]}-{ln.row}"),
            import_batch_id=batch.id, commit=False,
        )
        for j, pay in ln.payments:
            payments.record(ctx, loan.id, pay.model_copy(update={"idempotency_key": f"import-{p.sha256[:16]}-p{j}"}),
                            commit=False)
    audit.from_ctx(ctx, "import.committed", "import_batch", batch.id, batch.summary)
    db.commit()
    return {**summary(p), "batch_id": str(batch.id)}
