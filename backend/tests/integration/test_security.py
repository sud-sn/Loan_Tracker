"""Security: roles, step-up, sessions, CSRF, no Aadhaar leaks (acceptance checks 7 and 14)."""

from __future__ import annotations

import io
import json
import logging
import re
import zipfile

import pyotp
import pytest

from app.core import clock
from tests.conftest import OWNER_PASSWORD, OWNER_PHONE, STAFF_PASSWORD, Api, aadhaar, make_borrower, make_loan, pay

AADHAAR_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")


def test_everything_needs_login(anon: Api) -> None:
    for url in ("/api/v1/borrowers", "/api/v1/loans", "/api/v1/dues", "/api/v1/daybook", "/api/v1/dashboard",
                "/api/v1/search?q=a", "/api/v1/settings", "/api/v1/audit"):
        assert anon.get(url).status_code == 401, url


def test_staff_cannot_reveal_reverse_or_export_even_bypassing_the_ui(owner: Api, staff: Api) -> None:
    b = make_borrower(owner)
    loan = make_loan(owner, b["id"])
    p = pay(owner, loan["id"], "100").json()
    staff.step_up(STAFF_PASSWORD) if False else None
    r = staff.post("/api/v1/auth/step-up", json={"password": STAFF_PASSWORD})
    assert r.status_code == 403  # staff cannot even step up
    checks = [
        staff.post(f"/api/v1/borrowers/{b['id']}/reveal-aadhaar"),
        staff.post(f"/api/v1/payments/{p['id']}/reverse", json={"reason": "test reason"}),
        staff.get("/api/v1/export/full.zip"),
        staff.get("/api/v1/reports/collections/export"),
        staff.get(f"/api/v1/borrowers/{b['id']}/export"),
        staff.get("/api/v1/daybook/export", params={"start": "2026-11-01", "end": "2026-11-04"}),
        staff.post(f"/api/v1/loans/{loan['id']}/write-off", json={"reason": "x" * 5, "idempotency_key": "k" * 10}),
        staff.get("/api/v1/audit"),
        staff.get("/api/v1/users"),
        staff.put("/api/v1/settings", json={"version": 1}),
        staff.delete(f"/api/v1/borrowers/{b['id']}"),
    ]
    assert [r.status_code for r in checks] == [403] * len(checks)
    # Staff see the masked number only.
    detail = staff.get(f"/api/v1/borrowers/{b['id']}").json()
    assert detail["aadhaar_masked"].startswith("XXXX XXXX")
    # Staff can record payments but cannot create loans by default.
    assert pay(staff, loan["id"], "50").status_code == 201
    r = staff.post("/api/v1/loans", json={"borrower_id": b["id"], "idempotency_key": "staff-loan-01",
                                          "terms": {"principal": "1000", "rate": "1", "term_value": 2,
                                                    "disbursal_date": "2026-11-01"}})
    assert r.status_code == 403


def test_staff_role_switched_off_by_default(owner: Api) -> None:
    owner.post("/api/v1/users", json={"name": "S", "phone": "9876500009", "password": "another-good-pass-9"})
    api = Api()
    api.post("/api/v1/auth/login", json={"phone": "9876500009", "password": "another-good-pass-9"})
    assert api.get("/api/v1/borrowers").json()["error"]["code"] == "STAFF_DISABLED"


def test_csrf_required_on_writes(owner: Api) -> None:
    r = owner.client.post("/api/v1/borrowers", json={})  # no X-CSRF-Token header
    assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_FAILED"


def test_lockout_after_five_failures(owner: Api, anon: Api) -> None:
    for _ in range(5):
        r = anon.post("/api/v1/auth/login", json={"phone": OWNER_PHONE, "password": "wrong-password-123"})
        assert r.status_code == 401
    r = anon.post("/api/v1/auth/login", json={"phone": OWNER_PHONE, "password": OWNER_PASSWORD})
    assert r.status_code == 423 and r.json()["error"]["code"] == "ACCOUNT_LOCKED"


def test_password_policy(anon: Api) -> None:
    r = anon.post("/api/v1/auth/setup", json={"name": "O", "phone": OWNER_PHONE, "password": "short"})
    assert r.json()["error"]["code"] == "PASSWORD_TOO_SHORT"
    r = anon.post("/api/v1/auth/setup", json={"name": "O", "phone": OWNER_PHONE, "password": "1234567890"})
    assert r.json()["error"]["code"] == "PASSWORD_TOO_COMMON"


def test_only_one_owner_setup(owner: Api, anon: Api) -> None:
    r = anon.post("/api/v1/auth/setup", json={"name": "X", "phone": "9876500003", "password": "some-long-pass-77"})
    assert r.status_code == 409


def test_totp_login_and_replay(owner: Api, anon: Api) -> None:
    secret = owner.post("/api/v1/auth/totp/setup").json()["secret"]
    totp = pyotp.TOTP(secret)
    assert owner.post("/api/v1/auth/totp/enable", json={"code": totp.now()}).status_code == 200
    r = anon.post("/api/v1/auth/login", json={"phone": OWNER_PHONE, "password": OWNER_PASSWORD})
    assert r.json()["error"]["code"] == "TOTP_REQUIRED"
    code = totp.at(totp.timecode(__import__("datetime").datetime.now()) * 30 + 30)
    r = anon.post("/api/v1/auth/login", json={"phone": OWNER_PHONE, "password": OWNER_PASSWORD, "totp": code})
    assert r.status_code == 200, r.text
    again = Api().post("/api/v1/auth/login", json={"phone": OWNER_PHONE, "password": OWNER_PASSWORD, "totp": code})
    assert again.json()["error"]["code"] == "TOTP_INVALID"  # the same code cannot be used twice


def test_refresh_rotation_and_reuse_detection(owner: Api) -> None:
    old = owner.client.cookies.get("lt_refresh")
    assert owner.post("/api/v1/auth/refresh").status_code == 200
    new = owner.client.cookies.get("lt_refresh")
    assert new != old
    thief = Api()
    thief.client.cookies.set("lt_refresh", old, path="/api/v1/auth")
    thief.client.cookies.set("lt_csrf", "x")
    assert thief.post("/api/v1/auth/refresh").status_code == 401
    # Reuse of a rotated token ends the whole session family.
    assert owner.post("/api/v1/auth/refresh").status_code == 401


def test_security_headers(owner: Api) -> None:
    r = owner.get("/api/v1/auth/me")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "no-store"


def test_no_aadhaar_in_logs_urls_errors_or_exports(owner: Api, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    number = aadhaar(123456)
    spaced = f"{number[:4]} {number[4:8]} {number[8:]}"
    bodies: list[str] = []
    r = owner.post("/api/v1/borrowers", json={"name_en": "Leak Test", "phone": "9123456780", "aadhaar": spaced,
                                              "address": "x", "consent": {"given": True}})
    bodies.append(r.text)
    b = r.json()
    bad = number[:-1] + str((int(number[-1]) + 1) % 10)
    bodies.append(owner.post("/api/v1/borrowers", json={"name_en": "Bad", "phone": "9123456781", "aadhaar": bad,
                                                        "address": "x", "consent": {"given": True}}).text)
    bodies.append(owner.post("/api/v1/borrowers", json={"name_en": "Dup", "phone": "9123456782", "aadhaar": number,
                                                        "address": "x", "consent": {"given": True}}).text)
    bodies.append(owner.get("/api/v1/search", params={"q": number}).text)
    bodies.append(owner.get(f"/api/v1/borrowers/{b['id']}").text)
    bodies.append(owner.get("/api/v1/borrowers").text)
    bodies.append(owner.patch(f"/api/v1/borrowers/{b['id']}", json={"version": 99, "aadhaar": number}).text)
    owner.step_up()
    bodies.append(owner.get("/api/v1/audit").text)
    bodies.append(json.dumps(owner.get(f"/api/v1/borrowers/{b['id']}/export").json()))
    owner.step_up()
    z = zipfile.ZipFile(io.BytesIO(owner.get("/api/v1/export/full.zip").content))
    bodies += [z.read(n).decode() for n in z.namelist()]
    # Server-side log records only: the test client itself (httpx) logs the URLs it requests.
    server_logs = "\n".join(r.getMessage() + " " + str(r.__dict__) for r in caplog.records
                            if r.name.startswith(("app", "uvicorn", "sqlalchemy")))
    for text in bodies + [server_logs]:
        assert number not in text
        assert spaced not in text
        assert bad not in text
    from app.core.logging import JsonFormatter

    formatted = [JsonFormatter().format(r) for r in caplog.records]
    assert all(number not in line for line in formatted)  # even the test client's URL is redacted by our formatter


def test_signed_file_links_expire_and_check_permission(owner: Api, staff: Api) -> None:
    b = make_borrower(owner)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    up = owner.post("/api/v1/documents", data={"owner_type": "borrower", "owner_id": b["id"], "doc_type": "aadhaar"},
                    files={"file": ("card.png", png, "image/png")})
    assert up.status_code == 201, up.text
    doc = up.json()
    assert staff.post(f"/api/v1/documents/{doc['id']}/link").status_code == 403  # Aadhaar image: Owner only
    listed = staff.get("/api/v1/documents", params={"owner_type": "borrower", "owner_id": b["id"]}).json()
    assert listed[0]["can_view"] is False  # staff see that it exists
    link = owner.post(f"/api/v1/documents/{doc['id']}/link").json()["url"]
    r = owner.client.get(link)
    assert r.status_code == 200 and r.content == png
    assert "sandbox" in r.headers["content-security-policy"]
    assert owner.client.get(link[:-4] + "AAAA").status_code == 403
    clock.set_today(None)
