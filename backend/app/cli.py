"""Operator commands: ``python -m app.cli <command>``.

init-secrets   create the Aadhaar keyring and an env file with fresh random secrets
rotate-key     add a new master key, make it active and re-wrap every stored data key
rebuild-cache  recompute cached ledger columns from the ledger and report drift
reconcile      check the daily log against payments, loans and cash entries
seed-demo      fill the test copy with invented borrowers and loans (never real data)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def init_secrets(keyring_path: Path, env_path: Path | None) -> None:
    from app.security.crypto import Keyring

    if keyring_path.exists():
        sys.exit(f"{keyring_path} already exists; refusing to overwrite a master key")
    keyring_path.parent.mkdir(parents=True, exist_ok=True)
    keyring_path.write_text(json.dumps(Keyring.generate(), indent=2))
    os.chmod(keyring_path, 0o600)
    print(f"wrote {keyring_path} (keep a recovery copy offline, NOT with the backups)")
    if env_path:
        lines = [
            f"LT_AADHAAR_HMAC_SECRET={secrets.token_urlsafe(48)}",
            f"LT_SESSION_SECRET={secrets.token_urlsafe(48)}",
            f"LT_FILE_LINK_SECRET={secrets.token_urlsafe(48)}",
        ]
        with env_path.open("a") as fh:
            fh.write("\n".join(lines) + "\n")
        os.chmod(env_path, 0o600)
        print(f"appended secrets to {env_path}")


def rotate_key() -> None:
    from sqlalchemy import select

    from app.config import get_settings
    from app.db import get_sessionmaker
    from app.models import Borrower, User
    from app.security import crypto

    path = get_settings().keyring_file
    raw = json.loads(path.read_text())
    kid = f"k{date.today():%Y%m}{secrets.token_hex(2)}"
    raw["keys"][kid] = base64.b64encode(AESGCM.generate_key(bit_length=256)).decode()
    raw["active"] = kid
    ring = crypto.Keyring(active=kid, keys={k: base64.b64decode(v) for k, v in raw["keys"].items()})
    db = get_sessionmaker()()
    count = 0
    for b in db.scalars(select(Borrower).where(Borrower.aadhaar_encrypted.is_not(None))):
        b.aadhaar_encrypted = crypto.rewrap(b.aadhaar_encrypted, crypto.AADHAAR, ring)  # type: ignore[arg-type]
        count += 1
    for u in db.scalars(select(User).where(User.totp_secret_encrypted.is_not(None))):
        u.totp_secret_encrypted = crypto.rewrap(u.totp_secret_encrypted, crypto.TOTP, ring)  # type: ignore[arg-type]
    tmp = path.with_suffix(".new")
    tmp.write_text(json.dumps(raw, indent=2))
    os.chmod(tmp, 0o600)
    db.flush()
    os.replace(tmp, path)  # the new key is on disk before the re-wrapped rows are committed
    db.commit()
    print(f"active key is now {kid}; re-wrapped {count} Aadhaar records. Old keys stay in the keyring "
          f"until you remove them after the next verified backup.")


def rebuild_cache() -> int:
    from sqlalchemy import select

    from app.db import get_sessionmaker
    from app.models import Loan
    from app.services import ledger

    db = get_sessionmaker()()
    drift: list[str] = []
    for loan_id in db.scalars(select(Loan.id)):
        drift += ledger.rebuild_item_cache(db, loan_id, fix=True)
    db.commit()
    print("\n".join(drift) or "no drift")
    return len(drift)


def reconcile() -> int:
    from app.db import get_sessionmaker
    from app.services import daybook

    db = get_sessionmaker()()
    r = daybook.reconcile(db, date(1900, 1, 1), date(2999, 12, 31))
    print(r)
    return 0 if r["view_in"] == r["source_in"] and r["view_out"] == r["source_out"] else 1


FIRST = ["Murugan", "Lakshmi", "Selvi", "Karthik", "Anitha", "Ramesh", "Kavitha", "Suresh", "Meena", "Arun",
         "Divya", "Senthil", "Revathi", "Prakash", "Gowri", "Vijay", "Malar", "Bala", "Priya", "Kannan"]
FIRST_TA = ["முருகன்", "லட்சுமி", "செல்வி", "கார்த்திக்", "அனிதா", "ரமேஷ்", "கவிதா", "சுரேஷ்", "மீனா", "அருண்",
            "திவ்யா", "செந்தில்", "ரேவதி", "பிரகாஷ்", "கௌரி", "விஜய்", "மலர்", "பாலா", "பிரியா", "கண்ணன்"]
INITIAL = ["K", "S", "M", "R", "P", "V", "A", "T"]


def _fake_aadhaar(n: int) -> str:
    from app.security.verhoeff import check_digit

    body = f"{2 + n % 7}{n:010d}"[:11]
    return body + check_digit(body)


def seed_demo(borrowers: int, loans_per: int) -> None:
    """Invented people only (PRD section 13)."""
    from app.config import get_settings
    from app.core import clock
    from app.db import get_sessionmaker
    from app.deps import Ctx, load_business
    from app.models import User
    from app.schemas.borrowers import BorrowerIn, ConsentIn
    from app.schemas.loans import LoanCreateIn, PaymentIn, TermsIn
    from app.services import borrowers as borrower_service
    from app.services import loans as loan_service
    from app.services import payments as payment_service

    if get_settings().env == "production":
        sys.exit("seed-demo refuses to run with LT_ENV=production")
    from sqlalchemy import select

    db = get_sessionmaker()()
    owner = db.scalars(select(User).where(User.role == "owner")).first()
    if owner is None:
        sys.exit("create the owner account first (open the app and complete setup)")
    ctx = Ctx(db=db, user=owner, business=load_business(db), ip=None, user_agent="seed", request_id=None)
    rng = secrets.SystemRandom()
    today = clock.today()
    for n in range(borrowers):
        i = n % len(FIRST)
        b = borrower_service.create(ctx, BorrowerIn(
            name_en=f"{FIRST[i]} {INITIAL[n % len(INITIAL)]}", name_ta=f"{FIRST_TA[i]}" if n % 3 else None,
            phone=f"9{(700000000 + n * 7919) % 1000000000:09d}", aadhaar=_fake_aadhaar(n + 1000),
            address=f"{n + 1}, Test Street, Demo Nagar", preferred_language="ta" if n % 2 else "en",
            consent=ConsentIn(given=True), confirm_duplicate=True,
        ))
        for k in range(loans_per):
            months_ago = rng.randint(0, 11)
            disbursed = today - timedelta(days=30 * months_ago + rng.randint(0, 20))
            method = rng.choice(["reducing", "flat", "interest_only", "fixed_amount"])
            terms = TermsIn(principal=Decimal(rng.choice([10000, 25000, 50000, 100000])), rate=Decimal("2"),
                            term_value=12, method=method, disbursal_date=disbursed,
                            fixed_installment=Decimal("5000") if method == "fixed_amount" else None)
            loan = loan_service.create(ctx, LoanCreateIn(borrower_id=b.id, terms=terms,
                                                         idempotency_key=f"seed-{n}-{k}-{secrets.token_hex(4)}"))
            from app.services import ledger

            due = ledger.load_items(db, loan.id)
            for item in due:
                if item.due_date < today and rng.random() < 0.8:
                    paid_on = min(item.due_date + timedelta(days=rng.randint(0, 9)), today)
                    payment_service.record(ctx, loan.id, PaymentIn(
                        amount=Decimal(item.installment) / 100, paid_on=paid_on, idempotency_key=f"seed-pay-{item.id}"))
    print(f"seeded {borrowers} invented borrowers")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init-secrets")
    p.add_argument("--keyring", type=Path, required=True)
    p.add_argument("--env-file", type=Path)
    sub.add_parser("rotate-key")
    sub.add_parser("rebuild-cache")
    sub.add_parser("reconcile")
    p = sub.add_parser("seed-demo")
    p.add_argument("--borrowers", type=int, default=40)
    p.add_argument("--loans-per", type=int, default=1)
    args = parser.parse_args()
    if args.cmd == "init-secrets":
        init_secrets(args.keyring, args.env_file)
    elif args.cmd == "rotate-key":
        rotate_key()
    elif args.cmd == "rebuild-cache":
        sys.exit(1 if rebuild_cache() else 0)
    elif args.cmd == "reconcile":
        sys.exit(reconcile())
    elif args.cmd == "seed-demo":
        seed_demo(args.borrowers, args.loans_per)


if __name__ == "__main__":
    main()
