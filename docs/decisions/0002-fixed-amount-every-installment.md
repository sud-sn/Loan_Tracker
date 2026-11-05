# 0002 · Fixed amount every installment (owner's request)

**Status:** accepted

The owner asked for borrowers who say "I will pay a fixed amount every month", with a toggle while
entering the loan, and the app working out the rest.

**Decision.** A toggle on the Terms step ("Borrower wants a fixed amount every month/week/day")
offers three ways:

| Choice | Lender enters | App works out | Engine method |
| --- | --- | --- | --- |
| The amount | amount per installment | number of installments; last one smaller | `fixed_amount` |
| The period | months / weeks / days | the fixed installment | `flat` or `reducing` |
| Set interest and principal | principal and interest per installment (rows editable) | number of installments; last row absorbs the rest | `custom` |

For the first two, *Interest inside each payment* is either **same every time** (flat, on the amount
lent) or **on the remaining balance** (reducing). Rules:

- An amount that does not cover the interest is refused with the minimum shown.
- If a fixed installment would leave less than ₹1 for an extra installment, that paisa is folded into
  the last one, so there is never a ₹0.01 installment.
- Custom rows must add up to the principal exactly; the screen shows the difference while editing.
- For the maximum-rate warning, flat-style loans are compared by their flat monthly equivalent (total
  interest ÷ principal ÷ months); reducing-style loans by the nominal rate.

Example (unit-tested): ₹1,00,000 at 2% a month, ₹10,000 a month, same interest: 12 × (₹8,000 +
₹2,000), then ₹4,000 + ₹2,000 in month 13.
