"""Concurrency-safe sequences for borrower codes, loan numbers and receipt numbers.

One atomic ``INSERT ... ON CONFLICT DO UPDATE ... RETURNING`` takes a row lock on the counter,
so simultaneous requests are serialised; the unique constraints on the generated codes are a
second line of defence (PRD section 3). If a transaction rolls back, its increment rolls back
with it, so a number is only ever issued once, to a record that was actually saved.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

_SQL = text(
    """
    INSERT INTO counter (id, name, year, last_value, created_at, updated_at)
    VALUES (gen_random_uuid(), :name, :year, 1, now(), now())
    ON CONFLICT (name, year) DO UPDATE SET last_value = counter.last_value + 1, updated_at = now()
    RETURNING last_value
    """
)


def next_value(db: Session, name: str, year: int = 0) -> int:
    return int(db.execute(_SQL, {"name": name, "year": year}).scalar_one())


def next_borrower_code(db: Session) -> str:
    return f"BRW-{next_value(db, 'borrower'):06d}"


def next_loan_no(db: Session, year: int) -> str:
    return f"LN-{year}-{next_value(db, 'loan', year):06d}"


def next_receipt_no(db: Session, year: int) -> str:
    return f"RCT-{year}-{next_value(db, 'receipt', year):06d}"
