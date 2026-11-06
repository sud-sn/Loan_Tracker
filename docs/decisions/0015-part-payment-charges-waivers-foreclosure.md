# 0015 · Part payment, charges after the loan, waivers, foreclosure (Phase 2)

**Status:** accepted (owner's instruction, 6 Nov 2026: "Yes" to Phase 2 with the proposed defaults)

| Topic | Rule | Default |
| --- | --- | --- |
| Part payment | What is due on the day (charges, late fee, installments due) is paid first; the extra goes to principal. The installments not yet due are **replaced** by new ones on the same dates: a lower installment (same months) or the same installment (fewer months). Interest of the period the extra was paid in is split by days between the old and new figure. Interest already paid in advance on replaced rows is credited to the first new ones. Not for single-payment or custom-split loans. | lower installment |
| History | Replaced installments stay visible as "Rescheduled" with what was paid on them; nothing more is due on them and they can never be un-replaced. Each part payment is kept (old → new installment, count, last date, interest saved). | — |
| Database rule | Principal = what was paid or waived on replaced rows + the principal of the current rows (checked at commit). A payment whose money sits on replaced rows cannot be reversed. | — |
| Charges after the loan is given | Bounce, seizure/towing, legal notice, valuation, insurance paid for the borrower, other. Owed from the day added. **Payments pay charges first**, then late fee, interest, principal. All or part can be waived with a reason. A loan does not close while a charge is unpaid. | bounce ₹500 |
| Late-fee waiver | All or part of the late fee due today, oldest installment first, with a reason; booked as an adjustment (append-only). | — |
| Foreclosure charge | % of the principal being repaid when closing early; the owner can change it or type 0. Booked as a charge and paid by the closing payment. | 2 % |
| Interest when closing early | *Interest to today only* (the rule since ADR-0004), *Rule of 78* (total interest × k(k+1)/n(n+1) back, k = installments after the current period), or *no rebate*. | interest to today |
