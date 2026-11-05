# 0005 · Late fee computed at read time

**Status:** accepted · PRD §6 requires statuses to be right even if the nightly job fails

- The late fee is worked out from the schedule and the payment history whenever it is needed. The
  nightly job only stores a snapshot (`penalty_accrual`).
- *Fixed amount per day*: per loan, per day the loan has an overdue installment (not per
  installment).
- *% per month*: on each overdue installment's unpaid principal + interest; one day = 1/30 of a month;
  never on earlier late fees (no compounding).
- A day counts as late if the installment was unpaid at the start of that day; a payment counts from
  the next day. Reversed payments are ignored. Optional grace days.
- Off by default (owner's open question 3).
