# 0013 · Laptop first

**Status:** accepted (owner's instruction, 5 Nov 2026)

The PRD says the phone is the main device. After seeing the first screens, the owner asked for the
product to work first as a web page on a laptop, with screens that fit the window and no stray
elements in the middle. The app is now laptop-first and still works on a phone:

- A sidebar plus full-width pages (capped at 1800 px only on very large monitors).
- Data tables for borrowers and loans; one-line rows for the due lists; two-column loan and borrower
  pages; the new-loan form beside a live result panel; settings cards flowing in two columns.
- Panels adapt to the space they actually get (CSS container queries), so the same list is a card
  in a narrow column and a single line in a wide one.
- No floating bars over forms on a laptop; nothing reserved as empty space.
- Phones keep the bottom bar, cards and large touch targets; the end-to-end tests run on both
  (1366 × 768 and 360 px).
