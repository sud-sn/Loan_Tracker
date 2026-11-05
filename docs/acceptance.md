# Acceptance checks (PRD section 15) — status

Verified on 5 Nov 2026 in the development container with invented data. ✅ = passes an automated
check · ◐ = partly met · ⏳ = must be done on the owner's machine.

| # | Check | Status | How it is checked |
| --- | --- | --- | --- |
| 1 | `BRW-000001`, `BRW-000002`; 100 simultaneous creates → 100 unique codes | ✅ | `backend/tests/integration/test_borrowers.py` (25 threads, 100 creates) |
| 2 | ₹1,00,000 at 2%/month for 12 months matches §4 to the paisa; flat, interest-only, 90-day fixtures | ✅ | `tests/unit/test_engine_schedule.py` (+ property tests), `test_loans_payments.py` through the API |
| 3 | Schedule preview updates in under 200 ms | ✅ | server preview of 360 installments < 200 ms (test); the form waits 120 ms after typing |
| 4 | 10 days late → Overdue with 10 days; partial keeps it listed; full payment removes it | ✅ | `test_overdue_partial_and_full_payment`, e2e "10 days late shows in Overdue" (EN + TA) |
| 5 | No payment for 31 days → Long unpaid | ✅ | `test_long_unpaid_after_31_days` |
| 6 | Search by English part, Tamil part, code, phone, last 4 Aadhaar, < 300 ms at 50,000 borrowers | ✅ | `test_search_by_every_key`; measured p95 8–49 ms at 50,000 borrowers / 200,000 loans (below) |
| 7 | Staff cannot see full Aadhaar, reverse, or export; 403 even bypassing the UI | ✅ | `test_staff_cannot_reveal_reverse_or_export_even_bypassing_the_ui` (11 endpoints) |
| 8 | EN ↔ TA without reload, no missing key, nothing cut off at 360 px, Tamil PDF receipt | ✅ | `npm run i18n:check` (both directions + keys used in code), e2e overflow checks at 360 px and 1366 px, `test_receipt_pdf_renders_in_both_languages` |
| 9 | Executable renamed `.pdf` and the EICAR file rejected | ✅ | `test_upload_checks_content_not_extension` (ClamAV runs in production; tests use the EICAR-only scanner) |
| 10 | Same payment twice with one idempotency key → one payment | ✅ | `test_idempotency_key_creates_one_payment`, `test_simultaneous_payments_do_not_double_allocate` |
| 11 | Reversal re-opens the right installments; original stays visible | ✅ | `test_reversal_reopens_installments_and_keeps_original` |
| 12 | Restore drill on a clean machine: loans, payments, entries, documents back; Aadhaar decrypts | ⏳ | `infra/scripts/restore.sh` does it and checks every Aadhaar decrypts; run it before launch (runbook §5) |
| 13 | Lighthouse ≥ 90 for performance, accessibility (and PWA) on a mid-range phone | ◐ | accessibility **100**, best practices **100**, layout shift **0**, performance **86–89** (see decision 0010) |
| 14 | No Aadhaar number in logs, URLs, error responses or default exports | ✅ | `test_no_aadhaar_in_logs_urls_errors_or_exports` |
| 15 | Home page for a day: in, out, opening, closing; closing = opening + in − out | ✅ | `test_daybook_balance_in_out_and_reconciliation` (+ view vs source tables) |
| 16 | An expense in under 10 seconds, shown on the home page at once | ✅ | `test_expense_is_quick_and_shows_at_once`; 3 taps in the app |
| 17 | Toggle changes labels, statuses, categories, printed summaries; a Tamil-only name shows in Tamil in both languages | ✅ | screenshots; `displayName` falls back to the other script; loan summary PDF test in both languages |
| 18 | Not reachable from the public internet; only over the private VPN | ⏳ | Compose binds to the Tailscale address only and publishes no database port; check from outside (runbook §9) |
| 19 | 100 notebook loans import with preview, row-by-row errors, totals that match | ✅ | `test_import_100_notebook_loans_with_preview_and_errors`, `test_import_reports_errors_row_by_row` |

Also verified: the end-to-end tests pass on a laptop screen (1366 × 768) and at phone width (360 px)
in English and Tamil; layouts checked at 1280, 1366, 1440 and 1920 px with no sideways scrolling.

## Speed at the PRD's scale (p95, 20 runs each)

50,000 borrowers, 200,000 loans, 2,400,000 installments (99,000 overdue), one API process.

| Request | p95 |
| --- | --- |
| Search: part of English name / typo / part of Tamil name | 34 / 39 / 49 ms |
| Search: code / phone / last 4 Aadhaar / loan no. | 8 / 20 / 20 / 11 ms |
| Borrowers by name / with overdue | 77 / 268 ms |
| Due today / overdue / long unpaid | 81 / 256 / 48 ms |
| Daily log | 111 ms |
| Dashboard (from memory; about 0.75 s right after a change) | 6 ms |
| Borrowers sorted by outstanding (the one list above 300 ms) | 367 ms |

## Still to do before launch
- Tamil text review by a native speaker (decision 0011).
- Restore drill and the network check on the real machine (checks 12 and 18).
- Answers to the open questions in PRD §16 (current defaults in decision 0011).
