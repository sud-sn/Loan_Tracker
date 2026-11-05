# 0012 · Cached ledger columns

**Status:** accepted · PRD §11 (cached totals must be rebuildable)

`schedule_item.paid_*`, `waived_*`, `settled` and `loan.outstanding` / `last_payment_on` are a
cache of the allocations and adjustments, updated in the same transaction as each payment. This keeps
the due lists and search fast at 50,000 borrowers. `python -m app.cli rebuild-cache` recomputes them;
the nightly job does it and alerts on any drift, and a test checks that random payments and reversals
leave no drift.
