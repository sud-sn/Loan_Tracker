"""Database tables (PRD section 11). Money is BIGINT paise; dates are IST calendar days."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, Entity


def fk(target: str, *, nullable: bool = False, ondelete: str | None = None) -> Mapped[Any]:
    return mapped_column(UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable, index=True)


class BusinessSettings(Entity):
    """Single row of app settings (the "business" entity)."""

    __tablename__ = "business"

    licence_no: Mapped[str | None] = mapped_column(String(80))
    lender_name: Mapped[str | None] = mapped_column(String(120))
    lender_address: Mapped[str | None] = mapped_column(Text)
    max_rate_monthly: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    due_soon_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    due_window_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="7")
    long_unpaid_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    default_language: Mapped[str] = mapped_column(String(5), nullable=False, server_default="en")
    balance_start_date: Mapped[date | None] = mapped_column(Date)
    opening_balance: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    penalty_default_mode: Mapped[str] = mapped_column(String(12), nullable=False, server_default="off")
    penalty_default_value: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, server_default="0")
    penalty_grace_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    staff_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    staff_can_create_loans: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    daily_summary_time: Mapped[time | None] = mapped_column(Time, server_default="08:00")
    retention_years: Mapped[int] = mapped_column(Integer, nullable=False, server_default="8")
    max_upload_mb: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")
    max_files_per_owner: Mapped[int] = mapped_column(Integer, nullable=False, server_default="20")
    consent_notice_version: Mapped[str] = mapped_column(String(20), nullable=False, server_default="v1")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    __mapper_args__ = {"version_id_col": version}


class User(Entity):
    __tablename__ = "user"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    language: Mapped[str] = mapped_column(String(5), nullable=False, server_default="en")
    totp_secret_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (CheckConstraint("role in ('owner','staff')", name="role"),)


class RefreshToken(Entity):
    __tablename__ = "refresh_token"

    user_id: Mapped[uuid.UUID] = fk("user.id", ondelete="CASCADE")
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    ip: Mapped[str | None] = mapped_column(INET)


class Borrower(Entity):
    __tablename__ = "borrower"

    code: Mapped[str] = mapped_column(String(12), nullable=False, unique=True)
    name_en: Mapped[str | None] = mapped_column(String(150))
    name_ta: Mapped[str | None] = mapped_column(String(150))
    name_latin: Mapped[str] = mapped_column(String(300), nullable=False, server_default="")
    relation_name: Mapped[str | None] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(10), index=True)
    alt_phone: Mapped[str | None] = mapped_column(String(10))
    aadhaar_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    aadhaar_hash: Mapped[bytes | None] = mapped_column(LargeBinary, index=True)
    aadhaar_last4: Mapped[str | None] = mapped_column(String(4), index=True)
    address: Mapped[str | None] = mapped_column(Text)
    preferred_language: Mapped[str] = mapped_column(String(5), nullable=False, server_default="ta")
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="active")
    notes: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    erased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = fk("user.id", nullable=True)
    import_batch_id: Mapped[uuid.UUID | None] = fk("import_batch.id", nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    __mapper_args__ = {"version_id_col": version}

    guarantors: Mapped[list[Guarantor]] = relationship(back_populates="borrower", order_by="Guarantor.created_at")

    __table_args__ = (
        CheckConstraint("status in ('active','blocked','closed')", name="status"),
        CheckConstraint("name_en is not null or name_ta is not null or erased_at is not null", name="has_name"),
        CheckConstraint("preferred_language in ('en','ta')", name="language"),
        Index("ix_borrower_name_en_trgm", text("lower(name_en) gin_trgm_ops"), postgresql_using="gin"),
        Index("ix_borrower_name_ta_trgm", text("name_ta gin_trgm_ops"), postgresql_using="gin"),
        Index("ix_borrower_name_latin_trgm", text("name_latin gin_trgm_ops"), postgresql_using="gin"),
        Index("ix_borrower_phone_trgm", text("phone gin_trgm_ops"), postgresql_using="gin"),
    )


class Guarantor(Entity):
    __tablename__ = "guarantor"

    borrower_id: Mapped[uuid.UUID] = fk("borrower.id")
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(10))
    relation: Mapped[str | None] = mapped_column(String(60))
    borrower: Mapped[Borrower] = relationship(back_populates="guarantors")


class Consent(Entity):
    """DPDP consent record: notice shown, language, who recorded it and when. Append-only."""

    __tablename__ = "consent"

    borrower_id: Mapped[uuid.UUID] = fk("borrower.id")
    notice_version: Mapped[str] = mapped_column(String(20), nullable=False)
    language: Mapped[str] = mapped_column(String(5), nullable=False)
    method: Mapped[str] = mapped_column(String(12), nullable=False)  # verbal, signed
    recorded_by: Mapped[uuid.UUID] = fk("user.id")
    note: Mapped[str | None] = mapped_column(Text)


class ImportBatch(Entity):
    __tablename__ = "import_batch"

    created_by: Mapped[uuid.UUID] = fk("user.id")
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")


class Loan(Entity):
    __tablename__ = "loan"

    loan_no: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    borrower_id: Mapped[uuid.UUID] = fk("borrower.id")
    principal: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(9, 4), nullable=False)
    rate_basis: Mapped[str] = mapped_column(String(5), nullable=False)
    term_value: Mapped[int | None] = mapped_column(Integer)
    term_unit: Mapped[str] = mapped_column(String(12), nullable=False)
    frequency: Mapped[str] = mapped_column(String(8), nullable=False)
    method: Mapped[str] = mapped_column(String(14), nullable=False)
    fixed_style: Mapped[str | None] = mapped_column(String(8))
    fixed_installment: Mapped[int | None] = mapped_column(BigInteger)
    custom_principal: Mapped[int | None] = mapped_column(BigInteger)
    custom_interest: Mapped[int | None] = mapped_column(BigInteger)
    terms_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    installments: Mapped[int] = mapped_column(Integer, nullable=False)
    installment_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_interest: Mapped[int] = mapped_column(BigInteger, nullable=False)
    disbursal_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    first_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    maturity_date: Mapped[date] = mapped_column(Date, nullable=False)
    disbursal_mode: Mapped[str] = mapped_column(String(8), nullable=False, server_default="cash")
    penalty_mode: Mapped[str] = mapped_column(String(12), nullable=False, server_default="off")
    penalty_value: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, server_default="0")
    penalty_grace_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default="active", index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_on: Mapped[date | None] = mapped_column(Date)
    closed_reason: Mapped[str | None] = mapped_column(Text)
    last_payment_on: Mapped[date | None] = mapped_column(Date)
    # Cache of unpaid principal + interest (rebuildable from the ledger, see services.ledger).
    outstanding: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    principal_outstanding: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    # Due date of the oldest installment not yet fully paid (None when all are paid). It changes only
    # when a payment, reversal or waiver is saved, so overdue lists can work per loan, not per item.
    next_unpaid_due: Mapped[date | None] = mapped_column(Date)
    purpose: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    rate_warning_acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    idempotency_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    created_by: Mapped[uuid.UUID | None] = fk("user.id", nullable=True)
    import_batch_id: Mapped[uuid.UUID | None] = fk("import_batch.id", nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    __mapper_args__ = {"version_id_col": version}

    borrower: Mapped[Borrower] = relationship()
    items: Mapped[list[ScheduleItem]] = relationship(back_populates="loan", order_by="ScheduleItem.seq")

    __table_args__ = (
        CheckConstraint("principal > 0", name="principal_positive"),
        CheckConstraint("rate >= 0", name="rate_non_negative"),
        CheckConstraint("status in ('active','closed','written_off')", name="status"),
        CheckConstraint("rate_basis in ('month','year')", name="rate_basis"),
        CheckConstraint("frequency in ('monthly','weekly','daily','single')", name="frequency"),
        CheckConstraint(
            "method in ('reducing','flat','interest_only','simple_days','fixed_amount','custom')", name="method"
        ),
        CheckConstraint("disbursal_mode in ('cash','upi','bank','cheque','other')", name="disbursal_mode"),
        CheckConstraint("first_due_date >= disbursal_date", name="dates"),
        Index("ix_loan_borrower_status", "borrower_id", "status"),
        Index("ix_loan_active_next_unpaid", "next_unpaid_due",
              postgresql_where=text("status = 'active' AND deleted_at IS NULL")),
        Index(
            "ix_loan_active_last_activity", text("(coalesce(last_payment_on, disbursal_date))"),
            postgresql_where=text("status = 'active' AND deleted_at IS NULL"),
        ),
    )


class ScheduleItem(Entity):
    """One installment. Rows are locked once the loan is saved.

    The ``paid_*`` and ``waived_*`` columns are a cache of payment_allocation and
    loan_adjustment, updated in the same transaction as the payment and rebuildable at any time
    (``services.ledger.rebuild_item_cache``); a reconciliation test checks them.
    """

    __tablename__ = "schedule_item"

    loan_id: Mapped[uuid.UUID] = fk("loan.id")
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    installment: Mapped[int] = mapped_column(BigInteger, nullable=False)
    principal_part: Mapped[int] = mapped_column(BigInteger, nullable=False)
    interest_part: Mapped[int] = mapped_column(BigInteger, nullable=False)
    closing_balance: Mapped[int] = mapped_column(BigInteger, nullable=False)
    paid_principal: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    paid_interest: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    paid_penalty: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    waived_principal: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    waived_interest: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    waived_penalty: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    settled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    loan: Mapped[Loan] = relationship(back_populates="items")

    __table_args__ = (
        UniqueConstraint("loan_id", "seq", name="uq_schedule_item_loan_seq"),
        CheckConstraint("installment = principal_part + interest_part", name="installment_sum"),
        CheckConstraint("principal_part >= 0 and interest_part >= 0", name="parts_non_negative"),
        Index("ix_schedule_item_loan_due", "loan_id", "due_date"),
        Index("ix_schedule_item_unpaid_due", "due_date", "loan_id", postgresql_where=text("NOT settled")),
    )

    @property
    def principal_due(self) -> int:
        return self.principal_part - self.paid_principal - self.waived_principal

    @property
    def interest_due(self) -> int:
        return self.interest_part - self.paid_interest - self.waived_interest


class Payment(Entity):
    """Append-only ledger row. A reversal is its own row pointing at the payment it cancels."""

    __tablename__ = "payment"

    receipt_no: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    loan_id: Mapped[uuid.UUID] = fk("loan.id")
    kind: Mapped[str] = mapped_column(String(12), nullable=False, server_default="payment")
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reversed_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment.id"), unique=True
    )
    reversal_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = fk("user.id")

    allocations: Mapped[list[PaymentAllocation]] = relationship(back_populates="payment")

    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("kind in ('payment','reversal','settlement')", name="kind"),
        CheckConstraint("mode in ('cash','upi','bank','cheque','other')", name="mode"),
        CheckConstraint(
            "(kind = 'reversal') = (reversed_of_id is not null) and "
            "(kind <> 'reversal' or reversal_reason is not null)",
            name="reversal_fields",
        ),
    )


class PaymentAllocation(Entity):
    """How a payment was split. Reversal allocations are the exact negatives of the original."""

    __tablename__ = "payment_allocation"

    payment_id: Mapped[uuid.UUID] = fk("payment.id")
    schedule_item_id: Mapped[uuid.UUID] = fk("schedule_item.id")
    penalty_part: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    interest_part: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    principal_part: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    payment: Mapped[Payment] = relationship(back_populates="allocations")


class LoanAdjustment(Entity):
    """Waivers for early settlement and write-offs. Append-only, always with a reason."""

    __tablename__ = "loan_adjustment"

    loan_id: Mapped[uuid.UUID] = fk("loan.id")
    schedule_item_id: Mapped[uuid.UUID] = fk("schedule_item.id")
    payment_id: Mapped[uuid.UUID | None] = fk("payment.id", nullable=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    adjusted_on: Mapped[date] = mapped_column(Date, nullable=False)
    principal_part: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    interest_part: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    penalty_part: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = fk("user.id")

    __table_args__ = (
        CheckConstraint("kind in ('settlement_waiver','write_off')", name="kind"),
        CheckConstraint("principal_part >= 0 and interest_part >= 0 and penalty_part >= 0", name="non_negative"),
    )


class PenaltyAccrual(Entity):
    """Nightly snapshot of penalty accrued to date (a cache; the engine is the truth)."""

    __tablename__ = "penalty_accrual"

    loan_id: Mapped[uuid.UUID] = fk("loan.id")
    schedule_item_id: Mapped[uuid.UUID] = fk("schedule_item.id")
    accrual_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    __table_args__ = (UniqueConstraint("schedule_item_id", "accrual_date", name="uq_penalty_accrual_item_date"),)


class Document(Entity):
    __tablename__ = "document"

    owner_type: Mapped[str] = mapped_column(String(10), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime: Mapped[str] = mapped_column(String(60), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    scan_status: Mapped[str] = mapped_column(String(10), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[uuid.UUID] = fk("user.id")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("owner_type in ('borrower','loan')", name="owner_type"),
        CheckConstraint(
            "doc_type in ('aadhaar','pan','photo','address_proof','agreement','promissory_note','cheque','other')",
            name="doc_type",
        ),
        CheckConstraint("scan_status in ('clean','infected','pending','error')", name="scan_status"),
        Index("ix_document_owner", "owner_type", "owner_id"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    user_id: Mapped[uuid.UUID | None] = fk("user.id", nullable=True)
    action: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(30))
    entity_id: Mapped[str | None] = mapped_column(String(64), index=True)
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(300))
    request_id: Mapped[str | None] = mapped_column(String(40))
    __table_args__ = (Index("ix_audit_log_at", "at"),)


class Counter(Entity):
    __tablename__ = "counter"

    name: Mapped[str] = mapped_column(String(20), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    last_value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    __table_args__ = (UniqueConstraint("name", "year", name="uq_counter_name_year"),)


class Category(Entity):
    __tablename__ = "category"

    name_en: Mapped[str] = mapped_column(String(60), nullable=False)
    name_ta: Mapped[str] = mapped_column(String(60), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    __table_args__ = (CheckConstraint("kind in ('expense','income')", name="kind"),)


class CashEntry(Entity):
    """Hand-typed money in (other income) or out (own spending)."""

    __tablename__ = "cash_entry"

    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    category_id: Mapped[uuid.UUID] = fk("category.id")
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mode: Mapped[str] = mapped_column(String(8), nullable=False, server_default="cash")
    note: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    created_by: Mapped[uuid.UUID] = fk("user.id")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    __mapper_args__ = {"version_id_col": version}

    category: Mapped[Category] = relationship()

    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("direction in ('in','out')", name="direction"),
        CheckConstraint("mode in ('cash','upi','bank','other')", name="mode"),
    )


class CashEntryHistory(Entity):
    """Every create, edit and delete of a cash entry, as a full snapshot. Append-only."""

    __tablename__ = "cash_entry_history"

    cash_entry_id: Mapped[uuid.UUID] = fk("cash_entry.id")
    action: Mapped[str] = mapped_column(String(8), nullable=False)
    entry_version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    changed_by: Mapped[uuid.UUID] = fk("user.id")


class PushSubscription(Entity):
    __tablename__ = "push_subscription"

    user_id: Mapped[uuid.UUID] = fk("user.id", ondelete="CASCADE")
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(String(200), nullable=False)
    auth: Mapped[str] = mapped_column(String(100), nullable=False)


class JobRun(Entity):
    __tablename__ = "job_run"

    name: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")


__all__ = [
    "AuditLog",
    "Borrower",
    "BusinessSettings",
    "CashEntry",
    "CashEntryHistory",
    "Category",
    "Consent",
    "Counter",
    "Document",
    "Guarantor",
    "ImportBatch",
    "JobRun",
    "Loan",
    "LoanAdjustment",
    "Payment",
    "PaymentAllocation",
    "PenaltyAccrual",
    "PushSubscription",
    "RefreshToken",
    "ScheduleItem",
    "User",
]
