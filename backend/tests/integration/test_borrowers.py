"""Borrowers: codes, Aadhaar handling, duplicates, search (acceptance checks 1, 6, 7, 14)."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app.db import get_sessionmaker
from app.deps import Ctx, load_business
from app.models import Borrower, User
from app.schemas.borrowers import BorrowerIn
from app.services import borrowers as service
from tests.conftest import Api, aadhaar, borrower_payload, make_borrower


def test_codes_are_sequential(owner: Api) -> None:
    assert make_borrower(owner)["code"] == "BRW-000001"
    assert make_borrower(owner)["code"] == "BRW-000002"


def test_100_simultaneous_creates_give_100_unique_codes(owner: Api) -> None:
    sessions = get_sessionmaker()
    with sessions() as db:
        owner_id = db.query(User.id).scalar()
    lock = threading.Lock()
    payloads = [borrower_payload(phone=f"7{100000000 + i:09d}", aadhaar=aadhaar(90000 + i)) for i in range(100)]

    def create(data: dict) -> str:  # type: ignore[type-arg]
        with sessions() as db:
            ctx = Ctx(db=db, user=db.get(User, owner_id), business=load_business(db), ip=None, user_agent=None,  # type: ignore[arg-type]
                      request_id=None)
            b = service.create(ctx, BorrowerIn(**data))
            with lock:
                return b.code

    with ThreadPoolExecutor(max_workers=25) as pool:
        codes = list(pool.map(create, payloads))
    assert len(set(codes)) == 100
    assert sorted(codes) == [f"BRW-{i:06d}" for i in range(1, 101)]


def test_aadhaar_validation_and_masking(owner: Api) -> None:
    bad = owner.post("/api/v1/borrowers", json=borrower_payload(aadhaar="234567890123"))
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "AADHAAR_CHECKSUM"
    assert "234567890123" not in bad.text
    b = make_borrower(owner)
    assert b["aadhaar_masked"].startswith("XXXX XXXX ")
    assert "aadhaar" not in {k for k in b if k != "aadhaar_masked"}


def test_aadhaar_is_encrypted_with_separate_hash(owner: Api) -> None:
    number = aadhaar(4242)
    b = make_borrower(owner, aadhaar=number)
    with get_sessionmaker()() as db:
        row = db.get(Borrower, b["id"])
        assert row is not None and row.aadhaar_encrypted is not None
        assert number.encode() not in row.aadhaar_encrypted
        assert row.aadhaar_last4 == number[-4:]
        assert row.aadhaar_hash is not None and len(row.aadhaar_hash) == 32


def test_reveal_needs_owner_and_step_up_and_is_audited(owner: Api) -> None:
    number = aadhaar(777)
    b = make_borrower(owner, aadhaar=number)
    r = owner.post(f"/api/v1/borrowers/{b['id']}/reveal-aadhaar")
    assert r.status_code == 403 and r.json()["error"]["code"] == "STEP_UP_REQUIRED"
    owner.step_up()
    r = owner.post(f"/api/v1/borrowers/{b['id']}/reveal-aadhaar")
    assert r.status_code == 200 and r.json()["aadhaar"] == number
    owner.step_up()
    log = owner.get("/api/v1/audit", params={"action": "borrower.aadhaar_revealed"}).json()["items"]
    assert len(log) == 1


def test_duplicate_warning_owner_can_confirm(owner: Api, staff: Api) -> None:
    number = aadhaar(31337)
    make_borrower(owner, aadhaar=number, phone="9000011111")
    r = owner.post("/api/v1/borrowers", json=borrower_payload(aadhaar=number))
    assert r.status_code == 409 and r.json()["error"]["code"] == "DUPLICATE_BORROWER"
    assert r.json()["error"]["params"]["match"] == "aadhaar"
    r = owner.post("/api/v1/borrowers", json=borrower_payload(phone="9000011111"))
    assert r.json()["error"]["params"]["match"] == "phone"
    r = staff.post("/api/v1/borrowers", json=borrower_payload(aadhaar=number, confirm_duplicate=True))
    assert r.status_code == 409  # only the Owner can proceed
    r = owner.post("/api/v1/borrowers", json=borrower_payload(aadhaar=number, confirm_duplicate=True))
    assert r.status_code == 201


def test_name_rules_and_optimistic_locking(owner: Api) -> None:
    r = owner.post("/api/v1/borrowers", json=borrower_payload(name_en=None))
    assert r.status_code == 422
    b = make_borrower(owner, name_en=None, name_ta="செல்வி")
    assert b["name_ta"] == "செல்வி" and b["name_en"] is None
    ok = owner.patch(f"/api/v1/borrowers/{b['id']}", json={"version": b["version"], "name_en": "Selvi"})
    assert ok.status_code == 200
    stale = owner.patch(f"/api/v1/borrowers/{b['id']}", json={"version": b["version"], "notes": "x"})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "EDIT_CONFLICT"


def test_search_by_every_key(owner: Api) -> None:
    number = aadhaar(2468)
    b = make_borrower(owner, name_en="Murugan Kandasamy", name_ta="முருகன் கந்தசாமி", phone="9443012345",
                      aadhaar=number)
    for _ in range(5):
        make_borrower(owner)

    def found(q: str) -> bool:
        start = time.perf_counter()
        r = owner.get("/api/v1/search", params={"q": q})
        assert r.status_code == 200, r.text
        assert time.perf_counter() - start < 0.3
        return any(x["borrower_id"] == b["id"] for x in r.json())

    assert found("murug")  # part of English name, case-insensitive
    assert found("Kandasa")
    assert found("முருக")  # part of Tamil name
    assert found("Murgan")  # small typo
    assert found("murukan")  # spelling variant via the phonetic key
    assert found(b["code"])
    assert found("1")  # code number alone
    assert found("9443012345")
    assert found("30123")  # part of phone
    assert found(number[-4:])  # last 4 of Aadhaar
    r = owner.get("/api/v1/search", params={"q": number})
    assert r.status_code == 422  # a full Aadhaar number is never searched


def test_borrower_with_loan_cannot_be_deleted(owner: Api) -> None:
    from tests.conftest import make_loan

    b = make_borrower(owner)
    make_loan(owner, b["id"])
    assert owner.delete(f"/api/v1/borrowers/{b['id']}").json()["error"]["code"] == "BORROWER_HAS_LOANS"
    other = make_borrower(owner)
    assert owner.delete(f"/api/v1/borrowers/{other['id']}").status_code == 200
    assert owner.get(f"/api/v1/borrowers/{other['id']}").status_code == 404


def test_list_filters_and_sorting(owner: Api) -> None:
    make_borrower(owner, name_en="Zara")
    make_borrower(owner, name_en="Anand")
    names = [x["name_en"] for x in owner.get("/api/v1/borrowers", params={"sort": "name"}).json()["items"]]
    assert names == sorted(names, key=str.lower)
    assert owner.get("/api/v1/borrowers", params={"has_active_loan": True}).json()["total"] == 0
