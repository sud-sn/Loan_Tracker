# 0014 · Vehicle and land loans (Phase 1)

**Status:** accepted (owner's instruction, 6 Nov 2026: "start phase 1 with your defaults")

The business lends against vehicles and land, so the calculations now cover the money at the start
of such a loan.

| Topic | Rule | Default (Settings) |
| --- | --- | --- |
| Security | A loan can be given against a vehicle (registration, chassis, engine, make, year, price, down payment, insurance, lien on RC) or land (survey no., patta, extent, village/taluk/district, document no., guideline and market value, EC), with the originals kept. | none |
| Loan to value | Amount financed ÷ value. Value = valuation, else on-road price (vehicle), else market value, then guideline value (land). Above the limit the loan needs a ticked confirmation. | vehicle 75 %, land 50 % |
| Down payment | Price − down payment fills in the loan amount. | — |
| Charges | Processing fee, document charges, RTO/stamp, insurance, other. Each is *taken out* (borrower gets less in hand) or *added* (financed and repaid with the installments). Locked with the loan. | processing fee 0 %, document charges ₹0 |
| Amount handed over | Loan amount − charges taken out − extra days' interest collected − advance installments. | — |
| Daily log | Gross: the loan (amount financed) is money out; each charge and the advance installment payment are money in that day. The net is what was handed over. | — |
| Odd first period | Days beyond (or short of) one period are charged at the daily rate (monthly ÷ 30, yearly ÷ 365) on the first installment, or extra days collected when the loan is given. A short month counts as a full month. | on the first installment |
| Rounded EMI | Reducing and flat loans: the installment is rounded **up** to ₹1/5/10/50/100; the last one is smaller. Interest never goes up. | ₹10 |
| Advance EMIs | 0–12 installments due the day the loan is given (reducing and flat). Recorded as a payment with a receipt. On a reducing loan they carry no interest. | 0 |
| True cost | Internal rate of return of what the borrower actually receives and pays, counted in schedule periods; shown as % a month (reducing) and that × 12 a year. A plain loan shows its own rate. | — |
| Decimal rates | Rates such as 2.45 % a month are supported to 4 decimals. | — |

The API's own defaults are "no rounding, no advance, first period counted as full" so imports and
older clients are unchanged; the new-loan form starts from the owner's settings.

**Later phases:** part-prepayment with reschedule, charges ledger (bounce, seizure), late-fee
waiver, foreclosure charges (Phase 2); restructure, repossession and sale, closure with release of
documents, top-up, quarterly/half-yearly frequencies, cheque register, insurance alerts (Phase 3).
