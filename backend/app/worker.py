"""Background worker (PRD section 13): the nightly job at 00:05 IST and the daily summary push.

Status is always computed at read time, so a failed nightly job never makes a list wrong; the job
only refreshes cached values (penalty snapshots), checks the ledger caches for drift, purges files
deleted more than 30 days ago, and alerts the owner on any failure. It is safe to re-run.
"""

from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import IST, get_settings
from app.core import clock
from app.core.logging import configure
from app.db import get_sessionmaker
from app.deps import load_business
from app.engine import to_paise
from app.models import JobRun, Loan, PenaltyAccrual
from app.services import daybook, documents, dues, ledger, notify
from app.services import reports as _reports  # noqa: F401  (import check at start-up)

log = logging.getLogger("app.worker")
HEARTBEAT = Path("/tmp/worker-heartbeat")  # noqa: S108 - read by the container health check


def _record(db: Session, name: str, status: str, detail: dict[str, Any]) -> None:
    db.add(JobRun(name=name, run_date=clock.today(), status=status, finished_at=datetime.now(IST), detail=detail))
    db.commit()


def check_backup(db: Session) -> str:
    """A failed or missing backup alerts the owner (PRD section 13)."""
    path = get_settings().backup_status_file
    try:
        status = json.loads(path.read_text())
        finished = datetime.fromisoformat(status.get("finished_at", ""))
    except (OSError, ValueError):
        notify.alert(db, "Backup missing", f"No backup status found at {path}. Check the backup container.")
        return "missing"
    if status.get("status") != "ok":
        notify.alert(db, "Backup failed", str(status.get("detail", "see the backup container log")))
        return "failed"
    if (datetime.now(IST) - finished).total_seconds() > 26 * 3600:
        notify.alert(db, "Backup is late", f"The last backup finished at {finished:%d/%m/%Y %H:%M}.")
        return "late"
    return "ok"


def nightly() -> None:
    db = get_sessionmaker()()
    today = clock.today()
    detail: dict[str, object] = {}
    try:
        snapshots = 0
        for loan in db.scalars(select(Loan).where(Loan.status == "active", Loan.penalty_mode != "off",
                                                  Loan.deleted_at.is_(None))):
            items = ledger.load_items(db, loan.id)
            accrued = ledger.penalty_due(db, loan, items, today)
            for item in items:
                total = to_paise(accrued[item.id]) + item.paid_penalty + item.waived_penalty
                if total:
                    db.execute(insert(PenaltyAccrual).values(
                        loan_id=loan.id, schedule_item_id=item.id, accrual_date=today, amount=total,
                    ).on_conflict_do_update(constraint="uq_penalty_accrual_item_date", set_={"amount": total}))
                    snapshots += 1
        db.commit()
        detail["penalty_snapshots"] = snapshots
        drift: list[str] = []
        for loan_id in db.scalars(select(Loan.id).where(Loan.status == "active")):
            drift += ledger.rebuild_item_cache(db, loan_id, fix=True)
        db.commit()
        detail["cache_drift"] = len(drift)
        if drift:
            notify.alert(db, "Ledger cache drift fixed", "\n".join(drift[:50]))
        r = daybook.reconcile(db, today.replace(day=1), today)
        detail["daily_log_reconciled"] = r["view_in"] == r["source_in"] and r["view_out"] == r["source_out"]
        detail["documents_purged"] = documents.purge_expired(db)
        detail["counts"] = {k: v for k, v in dues.counts(db, load_business(db), today).items() if k != "ageing"}
        detail["backup"] = check_backup(db)
        # Rebuild the analytics star schema for the next day's charts and queries.
        from app.services import analytics

        detail["analytics_rows"] = sum(analytics.refresh(db)["rows"].values())
        _record(db, "nightly", "ok", detail)
    except Exception as exc:  # noqa: BLE001 - every failure must reach the owner
        db.rollback()
        log.error("nightly job failed", exc_info=exc)
        _record(db, "nightly", "failed", {"error": type(exc).__name__})
        notify.alert(db, "Nightly job failed", traceback.format_exc(limit=3))
    finally:
        db.close()


def daily_summary() -> None:
    """Runs every minute; sends once a day at the owner's chosen time (counts only, no names)."""
    db = get_sessionmaker()()
    try:
        business = load_business(db)
        now = datetime.now(IST)
        HEARTBEAT.write_text(now.isoformat())
        if business.daily_summary_time is None or now.time().replace(second=0, microsecond=0) < business.daily_summary_time:
            return
        today = clock.today()
        if db.scalars(select(JobRun).where(JobRun.name == "daily_summary", JobRun.run_date == today)).first():
            return
        c = dues.counts(db, business, today)
        body = f"{c['due_today']['count']} due today · {c['overdue']['count']} overdue · " \
               f"{c['long_unpaid']['count']} long unpaid. Open the app to see the lists."
        sent = notify.push_owner(db, "Loan Tracker", body)
        _record(db, "daily_summary", "ok", {"sent": sent})
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        log.error("daily summary failed", exc_info=exc)
    finally:
        db.close()


def main() -> None:
    configure(get_settings().log_level)
    scheduler = BlockingScheduler(timezone=IST)
    scheduler.add_job(nightly, CronTrigger(hour=0, minute=5, timezone=IST), id="nightly", max_instances=1,
                      coalesce=True, misfire_grace_time=6 * 3600)
    scheduler.add_job(daily_summary, CronTrigger(minute="*", timezone=IST), id="daily_summary", max_instances=1,
                      coalesce=True)
    log.info("worker started")
    scheduler.start()


if __name__ == "__main__":
    main()
