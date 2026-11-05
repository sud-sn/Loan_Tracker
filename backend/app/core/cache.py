"""A tiny in-process cache for read-heavy summaries (the dashboard).

Any commit that touches the ledger bumps a version number; cached values are keyed by it, so a
summary is recomputed after every payment, loan or cash entry and never shown stale. One API
process serves one owner, so in-process is enough.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

_lock = threading.Lock()
_version = 0
_store: dict[tuple[Any, ...], tuple[int, Any]] = {}
_LEDGER_TABLES = {"payment", "payment_allocation", "loan", "schedule_item", "loan_adjustment", "cash_entry",
                  "business"}


def version() -> int:
    return _version


def bump() -> None:
    global _version
    with _lock:
        _version += 1
        _store.clear()


def cached[T](key: tuple[Any, ...], compute: Callable[[], T]) -> T:
    v = _version
    hit = _store.get(key)
    if hit is not None and hit[0] == v:
        return hit[1]  # type: ignore[no-any-return]
    value = compute()
    with _lock:
        if _version == v:
            _store[key] = (v, value)
    return value


@event.listens_for(Session, "after_flush")
def _mark(session: Session, _ctx: Any) -> None:
    touched = {getattr(o, "__tablename__", "") for o in (*session.new, *session.dirty, *session.deleted)}
    if touched & _LEDGER_TABLES:
        session.info["ledger_changed"] = True


@event.listens_for(Session, "after_commit")
def _bump(session: Session) -> None:
    if session.info.pop("ledger_changed", False):
        bump()
