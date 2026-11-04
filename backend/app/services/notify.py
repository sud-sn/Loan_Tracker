"""Owner alerts and the daily summary push (PRD sections 6 and 13).

Nothing leaves the machine unless the owner configures it: email needs SMTP settings, web push
needs VAPID keys. Push payloads carry counts only — never names, phone numbers or amounts.
"""

from __future__ import annotations

import json
import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import PushSubscription, User

log = logging.getLogger("app.notify")


def email_owner(subject: str, body: str) -> bool:
    s = get_settings()
    if not (s.smtp_host and s.alert_email_to):
        log.warning("alert not emailed (SMTP not configured): %s", subject)
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = f"[Loan Tracker] {subject}", s.smtp_user or s.alert_email_to, s.alert_email_to
    msg.set_content(body)
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            if s.smtp_user and s.smtp_password:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        log.error("alert email failed: %s", type(exc).__name__)
        return False


def push_owner(db: Session, title: str, body: str) -> int:
    s = get_settings()
    if not (s.vapid_private_key and s.vapid_public_key):
        return 0
    from pywebpush import WebPushException, webpush

    sent = 0
    subs = db.scalars(
        select(PushSubscription).join(User, User.id == PushSubscription.user_id).where(User.role == "owner")
    ).all()
    for sub in subs:
        try:
            webpush(
                subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                data=json.dumps({"title": title, "body": body, "url": "/"}),
                vapid_private_key=s.vapid_private_key,
                vapid_claims={"sub": s.vapid_subject},
                ttl=3600,
            )
            sent += 1
        except WebPushException as exc:
            if exc.response is not None and exc.response.status_code in (404, 410):
                db.delete(sub)
            log.warning("push failed: %s", type(exc).__name__)
    db.commit()
    return sent


def alert(db: Session | None, subject: str, body: str) -> None:
    email_owner(subject, body)
    if db is not None:
        push_owner(db, subject, body)
