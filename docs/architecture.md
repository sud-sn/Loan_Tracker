# Architecture

A modular monolith on the owner's own machine (PRD section 14).

```
phone / laptop browser ── Tailscale (private) ──▶ Caddy (HTTPS, static PWA, /api proxy)
                                                     │
                                                     ▼
                                         FastAPI API (routers → services → repositories)
                                           │            │               │
                                     PostgreSQL 16   files volume    ClamAV (virus scan)
                                           ▲
                     worker (nightly 00:05 IST, daily summary) · backup (nightly, encrypted)
```

## Backend (`backend/app`)
- `engine/` — the pure interest engine: schedules (reducing, flat, interest-only, simple-days,
  fixed amount, custom split), allocation, late fee, statuses, settlement. No database or web imports;
  `Decimal` only. Fixtures from PRD §4 and property tests in `tests/unit`.
- `routers/` — HTTP only. `services/` — business rules. `repositories/` — heavier queries.
- `models/` + `alembic/` — tables. The database itself enforces the rules that matter most: payments,
  allocations, adjustments, consents and the audit log are append-only (triggers); allocations must
  add up to the payment; principal parts must add up to the loan; schedules and loan terms are locked
  once saved.
- Money is `BIGINT` paise in the database and `Decimal` in code. Dates are IST calendar days.

### Ledger and caches
The truth is the schedule plus payment allocations plus adjustments (waivers, write-offs). For speed,
each installment caches what was paid and waived, and each loan caches what is outstanding, its
unpaid principal, its oldest unpaid due date and its last payment date. All are updated in the same
transaction as the payment, rebuilt and checked nightly, and covered by a test (decision 0012).
Statuses, overdue days and late fees are always worked out when read, so they are right even if the
nightly job never ran.

### Security
See README and decision 0009: Argon2id passwords, optional authenticator codes, short JWT + rotating
refresh cookies, double-submit CSRF and Origin check, step-up for sensitive actions, lockout and rate
limits, Aadhaar envelope encryption (AES-256-GCM, data key per record, master key outside data and
backups) plus a keyed HMAC for duplicates, signed 5-minute document links, strict security headers,
logs that redact Aadhaar and phone numbers, and an append-only audit log.

### PDFs
WeasyPrint (Pango and HarfBuzz) with bundled Noto Sans and Noto Sans Tamil, so Tamil conjuncts and
vowel signs shape correctly. Receipts fit one A5 page.

## Frontend (`frontend/src`)
- React + TypeScript + Vite PWA, Tailwind with design tokens (`index.css`), shadcn-style components
  on Radix, TanStack Query, i18next.
- **Laptop first:** a sidebar plus full-width pages; data tables for lists; two-column detail pages;
  the new-loan form with a live result panel. Panels use container queries so they adapt to the space
  they get. Phones get a bottom bar, card lists and large touch targets.
- English is bundled; Tamil loads when chosen. `npm run i18n:check` keeps both files complete.
- The typed API client is generated from the backend's OpenAPI document.
- The service worker opens the app shell offline and keeps last-viewed data readable; saving needs a
  connection.
