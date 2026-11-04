"""Test setup: a real PostgreSQL database (PRD section 13), invented data only.

Set TEST_DATABASE_URL to point at a disposable database; it is migrated from scratch at the start
of the run and emptied before every test.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="lt-test-"))
os.environ.setdefault("TEST_DATABASE_URL", "postgresql+psycopg://postgres@localhost:5433/loantracker_test")
os.environ.update({
    "LT_ENV": "test",
    "LT_DATABASE_URL": os.environ["TEST_DATABASE_URL"],
    "LT_DATA_DIR": str(_TMP / "data"),
    "LT_KEYRING_FILE": str(_TMP / "keyring.json"),
    "LT_AADHAAR_HMAC_SECRET": "test-hmac-secret-that-is-long-enough-1234567890",
    "LT_SESSION_SECRET": "test-session-secret-that-is-long-enough-123456789",
    "LT_FILE_LINK_SECRET": "test-file-link-secret-that-is-long-enough-12345678",
    "LT_COOKIE_SECURE": "false",
    "LT_SCANNER": "builtin",
    "LT_APP_ORIGIN": "http://testserver",
    "LT_BACKUP_STATUS_FILE": str(_TMP / "backup-status.json"),
})

from app.security.crypto import Keyring  # noqa: E402

(_TMP / "keyring.json").write_text(json.dumps(Keyring.generate("ktest")))

from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from app.core import clock  # noqa: E402
from app.core.ratelimit import limiter  # noqa: E402
from app.db import get_engine, get_sessionmaker  # noqa: E402

TODAY = date(2026, 11, 4)
BACKEND = Path(__file__).resolve().parent.parent
OWNER_PHONE, OWNER_PASSWORD = "9876500001", "owner-pass-Kumar-2026"
STAFF_PHONE, STAFF_PASSWORD = "9876500002", "staff-pass-Selvi-2026"


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")
    with engine.begin() as conn:
        tables = [r[0] for r in conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT IN ('alembic_version')"))]
        conn.execute(text("CREATE TABLE IF NOT EXISTS _seed_category AS SELECT * FROM category"))
    os.environ["LT_TEST_TABLES"] = ",".join(t for t in tables if t != "_seed_category")
    yield


@pytest.fixture(autouse=True)
def clean(database: None) -> Iterator[None]:
    tables = [t for t in os.environ["LT_TEST_TABLES"].split(",") if t]
    with get_engine().begin() as conn:
        # Append-only triggers forbid TRUNCATE; replica mode skips triggers for test cleanup only.
        conn.execute(text("SET session_replication_role = replica"))
        conn.execute(text(f"TRUNCATE {', '.join(chr(34) + t + chr(34) for t in tables)} CASCADE"))
        conn.execute(text("INSERT INTO category SELECT * FROM _seed_category"))
        conn.execute(text("INSERT INTO business (id) VALUES (gen_random_uuid())"))
        conn.execute(text("SET session_replication_role = origin"))
    limiter.reset()
    clock.set_today(TODAY)
    yield
    clock.set_today(None)


class Api:
    """TestClient wrapper that sends the CSRF header like the real app does."""

    def __init__(self) -> None:
        from app.main import app

        self.client = TestClient(app, base_url="http://testserver")

    def _headers(self, extra: dict[str, str] | None) -> dict[str, str]:
        headers = dict(extra or {})
        csrf = self.client.cookies.get("lt_csrf")
        if csrf:
            headers["X-CSRF-Token"] = csrf
        return headers

    def get(self, url: str, **kw: Any) -> Any:
        return self.client.get(url, headers=self._headers(kw.pop("headers", None)), **kw)

    def post(self, url: str, **kw: Any) -> Any:
        return self.client.post(url, headers=self._headers(kw.pop("headers", None)), **kw)

    def put(self, url: str, **kw: Any) -> Any:
        return self.client.put(url, headers=self._headers(kw.pop("headers", None)), **kw)

    def patch(self, url: str, **kw: Any) -> Any:
        return self.client.patch(url, headers=self._headers(kw.pop("headers", None)), **kw)

    def delete(self, url: str, **kw: Any) -> Any:
        return self.client.delete(url, headers=self._headers(kw.pop("headers", None)), **kw)

    def step_up(self, password: str = OWNER_PASSWORD) -> None:
        r = self.post("/api/v1/auth/step-up", json={"password": password})
        assert r.status_code == 200, r.text


@pytest.fixture
def anon() -> Api:
    return Api()


@pytest.fixture
def owner() -> Api:
    api = Api()
    r = api.post("/api/v1/auth/setup", json={"name": "Owner", "phone": OWNER_PHONE, "password": OWNER_PASSWORD})
    assert r.status_code == 200, r.text
    return api


@pytest.fixture
def staff(owner: Api) -> Api:
    r = owner.get("/api/v1/settings")
    owner.put("/api/v1/settings", json={"version": r.json()["version"], "staff_enabled": True})
    r = owner.post("/api/v1/users", json={"name": "Staff", "phone": STAFF_PHONE, "password": STAFF_PASSWORD})
    assert r.status_code == 200, r.text
    api = Api()
    r = api.post("/api/v1/auth/login", json={"phone": STAFF_PHONE, "password": STAFF_PASSWORD})
    assert r.status_code == 200, r.text
    return api


def aadhaar(n: int) -> str:
    from app.security.verhoeff import check_digit

    body = f"{2 + n % 7}{n:010d}"[:11]
    return body + check_digit(body)


_counter = {"n": 0}


def borrower_payload(**kw: Any) -> dict[str, Any]:
    _counter["n"] += 1
    n = _counter["n"]
    data: dict[str, Any] = {
        "name_en": f"Test Person {n}", "phone": f"9{800000000 + n:09d}", "aadhaar": aadhaar(5000 + n),
        "address": f"{n}, Test Street, Madurai", "consent": {"given": True, "method": "verbal", "language": "ta"},
    }
    data.update(kw)
    return data


def make_borrower(api: Api, **kw: Any) -> dict[str, Any]:
    r = api.post("/api/v1/borrowers", json=borrower_payload(**kw))
    assert r.status_code == 201, r.text
    return dict(r.json())


def make_loan(api: Api, borrower_id: str, key: str | None = None, **terms: Any) -> dict[str, Any]:
    t: dict[str, Any] = {"principal": "100000.00", "rate": "2", "term_value": 12, "disbursal_date": "2026-01-05"}
    t.update(terms)
    _counter["n"] += 1
    r = api.post("/api/v1/loans", json={"borrower_id": borrower_id, "terms": t,
                                        "idempotency_key": key or f"loan-key-{_counter['n']:06d}"})
    assert r.status_code == 201, r.text
    return dict(r.json())


def pay(api: Api, loan_id: str, amount: str, key: str | None = None, **kw: Any) -> Any:
    _counter["n"] += 1
    body = {"amount": amount, "idempotency_key": key or f"pay-key-{_counter['n']:06d}", **kw}
    return api.post(f"/api/v1/loans/{loan_id}/payments", json=body)


@pytest.fixture
def db() -> Iterator[Any]:
    session = get_sessionmaker()()
    yield session
    session.close()
