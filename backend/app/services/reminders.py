"""Polite, factual reminder text and one-tap Call / WhatsApp links (PRD sections 6 and 12)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.core import clock, i18n
from app.models import BusinessSettings, Loan
from app.services import ledger


def for_loan(db: Session, loan: Loan, business: BusinessSettings) -> dict[str, Any]:
    b = loan.borrower
    lang = b.preferred_language
    today = clock.today()
    items = ledger.load_items(db, loan.id)
    s = ledger.summary(db, loan, items, today, business.due_soon_days)
    name = i18n.name(lang, b.name_en, b.name_ta)
    if s.overdue_amount > 0:
        oldest = min(it.due_date for it in items if not it.settled and it.due_date < today)
        message = i18n.t(lang, "reminder.overdue", name=name, loan=loan.loan_no, date=i18n.fmt_date(oldest),
                         amount=i18n.money(s.overdue_amount + s.due_today_amount))
    elif s.next_due_date is not None:
        message = i18n.t(lang, "reminder.due", name=name, loan=loan.loan_no, date=i18n.fmt_date(s.next_due_date),
                         amount=i18n.money(s.next_due_amount))
    else:
        message = i18n.t(lang, "reminder.general", name=name, loan=loan.loan_no,
                         amount=i18n.money(s.total_outstanding))
    phone = b.phone
    return {
        "phone": phone,
        "language": lang,
        "message": message,
        "whatsapp_url": f"https://wa.me/91{phone}?text={quote(message)}" if phone else None,
        "tel_url": f"tel:+91{phone}" if phone else None,
    }
