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

## Every screen size (added 5 Nov 2026)

| Screen | Menu | Page |
| --- | --- | --- |
| Phone (< 768 px) | Bottom bar | One column, cards |
| Tablet (768-1023 px) | Left rail: icons with short labels | Cards, 2-column panels |
| Laptop (1024 px+) | Full left menu, 14-18 rem wide; the owner can fold it into the rail, remembered per browser | Tables, side-by-side panels |
| Large monitor (1600 px+) | Same; text, buttons and the menu grow gently (16 px up to 18 px at 2400 px) | Uses the full width; at 110 rem and wider, today's log sits beside "who has to pay" and settings use 3 columns |
| Ultrawide | Same | Lists and detail pages fill the screen; forms stay a readable 110 rem, centred |

Panels that must react to the space they actually get (also when the menu is folded) use container
queries on `main` (`@container/main`) rather than the window width. Checked at 13 sizes from 768 to
3440 px in English and Tamil; the end-to-end tests run on a phone, tablet, laptop and 1920 px monitor.

