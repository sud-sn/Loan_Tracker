from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import Lang, Money, Schema

BorrowerStatus = Literal["active", "blocked", "closed"]


class GuarantorIn(Schema):
    name: str = Field(min_length=1, max_length=150)
    phone: str | None = Field(default=None, max_length=16)
    relation: str | None = Field(default=None, max_length=60)


class GuarantorOut(GuarantorIn):
    id: uuid.UUID


class ConsentIn(Schema):
    given: bool
    method: Literal["verbal", "signed"] = "verbal"
    language: Lang = "ta"
    note: str | None = Field(default=None, max_length=500)


class BorrowerIn(Schema):
    name_en: str | None = Field(default=None, max_length=150)
    name_ta: str | None = Field(default=None, max_length=150)
    relation_name: str | None = Field(default=None, max_length=150)
    phone: str = Field(min_length=10, max_length=16)
    alt_phone: str | None = Field(default=None, max_length=16)
    aadhaar: str = Field(min_length=12, max_length=14, repr=False)
    address: str = Field(min_length=1, max_length=1000)
    occupation: str | None = Field(default=None, max_length=80)
    town: str | None = Field(default=None, max_length=80)
    district: str | None = Field(default=None, max_length=60)
    pincode: str | None = Field(default=None, pattern=r"^\d{6}$")
    preferred_language: Lang = "ta"
    notes: str | None = Field(default=None, max_length=4000)
    guarantors: list[GuarantorIn] = Field(default_factory=list, max_length=5)
    consent: ConsentIn
    confirm_duplicate: bool = False

    @model_validator(mode="after")
    def _name(self) -> BorrowerIn:
        if not (self.name_en or self.name_ta):
            raise ValueError("NAME_REQUIRED")
        if not self.consent.given:
            raise ValueError("CONSENT_REQUIRED")
        return self


class BorrowerUpdateIn(Schema):
    version: int
    name_en: str | None = Field(default=None, max_length=150)
    name_ta: str | None = Field(default=None, max_length=150)
    relation_name: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, max_length=16)
    alt_phone: str | None = Field(default=None, max_length=16)
    aadhaar: str | None = Field(default=None, max_length=14, repr=False)
    address: str | None = Field(default=None, max_length=1000)
    occupation: str | None = Field(default=None, max_length=80)
    town: str | None = Field(default=None, max_length=80)
    district: str | None = Field(default=None, max_length=60)
    pincode: str | None = Field(default=None, pattern=r"^\d{6}$")
    preferred_language: Lang | None = None
    status: BorrowerStatus | None = None
    notes: str | None = Field(default=None, max_length=4000)
    guarantors: list[GuarantorIn] | None = Field(default=None, max_length=5)
    confirm_duplicate: bool = False


class ConsentOut(Schema):
    id: uuid.UUID
    notice_version: str
    language: Lang
    method: str
    note: str | None
    created_at: datetime


class BorrowerOut(Schema):
    id: uuid.UUID
    code: str
    name_en: str | None
    name_ta: str | None
    relation_name: str | None
    phone: str | None
    alt_phone: str | None
    aadhaar_masked: str | None
    address: str | None
    occupation: str | None = None
    town: str | None = None
    district: str | None = None
    pincode: str | None = None
    preferred_language: Lang
    status: BorrowerStatus
    notes: str | None
    profile_incomplete: bool
    version: int
    created_at: datetime
    guarantors: list[GuarantorOut]


class BorrowerTotals(Schema):
    outstanding: Money
    overdue_amount: Money
    overdue_days: int
    active_loans: int
    closed_loans: int
    overdue_loans: int
    last_payment_on: date | None


class BorrowerDetailOut(BorrowerOut):
    totals: BorrowerTotals
    consents: list[ConsentOut]


class BorrowerListItem(Schema):
    id: uuid.UUID
    code: str
    name_en: str | None
    name_ta: str | None
    phone: str | None
    status: BorrowerStatus
    outstanding: Money
    overdue_amount: Money
    overdue_days: int
    active_loans: int
    multiple_overdue: bool
    profile_incomplete: bool


class SearchResult(Schema):
    kind: Literal["borrower", "loan"]
    borrower_id: uuid.UUID
    loan_id: uuid.UUID | None = None
    loan_no: str | None = None
    code: str
    name_en: str | None
    name_ta: str | None
    phone: str | None
    outstanding: Money
    overdue: bool
    matched: str


class DuplicateMatch(Schema):
    code: str
    name_en: str | None
    name_ta: str | None
    match: Literal["aadhaar", "phone"]


class RevealOut(Schema):
    aadhaar: str
