# Loan Tracker · கடன் கணக்கு

A private, bilingual (English and Tamil) web app that replaces one lender's notebook. It records
borrowers and loans, builds every repayment schedule split into principal and interest, records
payments, keeps a daily log of money in and out, and shows at a glance who is due, overdue, or has
not paid for a long time.

It runs on your own computer or home server. The database and documents stay on that machine, and
only you can reach it, over your home network or a private VPN such as Tailscale. It is built for a
laptop browser first (full-width tables and side-by-side panels) and also works as an installable app
on a phone.

> Built from `Loan_Tracker___Product_Requirements.md` (4 Nov 2026). Decisions taken where the PRD
> was open are in [`docs/decisions/`](docs/decisions/). What is verified, and how, is in
> [`docs/acceptance.md`](docs/acceptance.md).

## What it does

- **Loans in under a minute**: amount, rate, term, and the full schedule appears as you type.
  The methods are reducing balance (EMI), flat, interest-only and simple interest for days, plus:
- **Fixed amount every installment**: a toggle for when the borrower says how much they can pay.
  - *The amount*: enter, say, ₹5,000 a month and the app works out how many months it takes.
    The last installment is smaller.
  - *The period*: pick the months and the app works out the fixed amount.
  - *Set interest and principal yourself*: for example ₹4,000 principal plus ₹1,000 interest each
    month. You can also edit any single row.
- **Who has to pay**: due today, overdue (grouped 1–7, 8–30, 31–60, 61–90 and 90+ days), long
  unpaid, and the next few days. Every row has **Call**, **WhatsApp reminder** (a polite message
  in the borrower's language) and **Record payment**.
- **Payments**: applied to the oldest installment first (late fee, then interest, then principal),
  with the split shown and a receipt in English or Tamil (PDF with proper Tamil shaping). Double
  taps never save twice. Reversals keep the original entry visible.
- **Today's log (home page)**: opening balance, money in, money out and closing balance, your own
  expenses and other income (each in a few taps), and week and month totals.
- **Borrowers**: unique `BRW-000001` codes, Aadhaar validated, encrypted and shown masked, a
  duplicate warning, consent record, documents (camera or gallery, virus-scanned), and search by
  name in either script, code, phone, loan number or the last 4 Aadhaar digits.
- **Reports**: collections, outstanding by borrower, overdue ageing, interest earned, borrower
  statement. Each exports to CSV and PDF in English or Tamil.
- **Notebook import**: a spreadsheet template, a preview with totals to compare with the notebook,
  and a row-by-row error report.

## Repository layout

```
backend/    FastAPI + SQLAlchemy + Alembic (Python 3.12). app/engine is the pure interest engine.
frontend/   React + TypeScript + Vite PWA, Tailwind design tokens, i18next (en.json, ta.json).
infra/      Docker Compose, Caddy, backup / restore / health scripts.
docs/       Runbook, architecture, decisions, acceptance status, Tamil glossary, privacy notice.
```

## Run it at home (production)

The full steps, including Tailscale, certificates, keys, backups and the restore drill, are in
[`docs/runbook.md`](docs/runbook.md). In short:

```bash
cp .env.example .env && chmod 600 .env        # fill it in
cd infra && docker compose --env-file ../.env build
docker run --rm -u 0 -v /srv/loantracker-keys:/keys loantracker-api:local \
  python -m app.cli init-secrets --keyring /keys/aadhaar_keyring.json --env-file /keys/secrets.env
cat /srv/loantracker-keys/secrets.env >> ../.env   # the three LT_*_SECRET values
docker compose --env-file ../.env up -d
```

Open `https://<your-tailnet-name>` on your phone, create the owner account, then use
**Add to Home screen** to install it.

## Develop

Requirements: Python 3.12, Node 22, PostgreSQL 16 (with `pg_trgm`).

```bash
# backend
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.lock && .venv/bin/pip install -e ".[dev]"
export LT_ENV=development LT_COOKIE_SECURE=false LT_SCANNER=builtin \
       LT_DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/loantracker_dev \
       LT_KEYRING_FILE=$HOME/.loantracker-dev/keyring.json LT_DATA_DIR=$HOME/.loantracker-dev/data
.venv/bin/python -m app.cli init-secrets --keyring $LT_KEYRING_FILE --env-file $HOME/.loantracker-dev/secrets.env
set -a; source $HOME/.loantracker-dev/secrets.env; set +a
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload            # http://127.0.0.1:8000/api/docs

# frontend (another terminal)
cd frontend && npm ci && npm run dev               # http://localhost:5173 (proxies /api)

# invented demo data for the test copy (never real people)
cd backend && .venv/bin/python -m app.cli seed-demo --borrowers 40
```

### Checks (the same ones CI runs)

```bash
cd backend  && ruff check app tests && mypy && TEST_DATABASE_URL=... pytest -q
cd frontend && npm run i18n:check && npm run lint && npm run typecheck && npm test && npm run build
cd frontend && npx playwright test                 # needs the API on :8000 and `npx vite preview` on :4173
```

- `npm run i18n:check` fails if a key exists in one language and not the other, or if the code
  uses a key that has no translation.
- After changing an API route, run `python -m app.export_openapi > openapi.json` in `backend/` and
  `npm run api:generate` in `frontend/` (CI checks both are up to date).
- To add a third language, add `frontend/src/i18n/<code>.json` and `backend/app/i18n/<code>.json`
  and list it in `LANGUAGES` (`frontend/src/i18n/index.ts`).

## Security in one paragraph

Aadhaar numbers are encrypted at application level (AES-256-GCM, one data key per record wrapped
by a master key kept outside the data and backup folders). A separate keyed HMAC finds duplicates,
the number is shown masked, and only the owner can reveal it, after re-entering the password; every
reveal is logged. Login is phone and password (Argon2id) with optional authenticator-app 2FA.
Sessions are HttpOnly, Secure, SameSite cookies with CSRF protection, lockout and rate limits. The
payment and audit tables are append-only, enforced in the database. Uploads are checked by
content, virus-scanned, stored under random names and opened only through 5-minute signed links.
Logs redact Aadhaar and phone numbers. The app is never exposed to the public internet. Details:
[`docs/architecture.md`](docs/architecture.md).
