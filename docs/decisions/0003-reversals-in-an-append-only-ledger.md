# 0003 · Reversals in an append-only ledger

**Status:** accepted · PRD §5 and §11 conflict ("amounts positive" vs "posts a negative entry")

- A reversal is its own `payment` row with `kind = reversal`, a **positive** amount, `reversed_of_id`
  and a mandatory reason. Its allocations are the exact negatives of the original's. Database checks
  keep the sums right and forbid UPDATE or DELETE on payments, allocations and the audit log.
- In the daily log a reversal is **negative money in on the day it was made**, so earlier days'
  closing balances never change.
- v1 does not reverse an *early settlement* payment or payments on a *written-off* loan (both close
  the loan with waivers); correct those by recording a new entry with a reason.
