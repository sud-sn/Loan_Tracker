# 0017 · A star schema for analytics, next to the ledger

**Status:** accepted (owner's request, 6 Nov 2026: "structure the tables … like a star schema … for
analytics … a dashboard with charts … query the data when we want")

**Decision.** The operational tables stay as they are: one table per thing, with the database rules
that keep the ledger exact (append-only payments, allocations that must add up, locked terms). A
separate read-only `analytics` schema holds a star schema of dimension and fact **materialized
views** built from them, rebuilt nightly and on demand. Charts and ad-hoc queries read only from
it.

**Why not reshape the operational tables into a star.** A star schema is shaped for reading and
summing, not for safe writing: it repeats data on purpose and cannot carry the ledger's rules.
Keeping both layers gives exact money *and* simple analytics, and lets the analytics change
without a risky migration of the ledger.

**Borrower profile.** Optional occupation, village/town, district and PIN code were added to the
borrower (form and API) so analysis can group by place and work. Aadhaar, phone numbers and
addresses are never copied into `analytics` (a test enforces it).

**Access.** `analytics_reader` reads `analytics` only. Details and example queries:
[`docs/analytics.md`](../analytics.md).
