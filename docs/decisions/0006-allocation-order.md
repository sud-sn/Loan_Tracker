# 0006 · Allocation order and back-dated payments

**Status:** accepted · PRD §5

- Oldest unpaid installment first; inside each installment: late fee, then interest, then principal;
  anything left goes to the next installment.
- A payment is split against whatever is unpaid when it is entered (allocations are append-only, so
  a back-dated payment does not re-split later ones). Notebook payments should be entered oldest
  first; the import does this automatically.
- A payment larger than everything still owed is refused.
