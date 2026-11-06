import { expect, test, type Page } from "@playwright/test";

// Main flows on a laptop, a large monitor, a tablet and at phone width, in English and Tamil: sign in, add a borrower, give a fixed-amount
// loan, record a payment, see an overdue loan. Every visited screen is checked for sideways
// overflow and for untranslated keys. Invented data only.

const OWNER = { name: "Owner", phone: "9876500001", password: "owner-pass-Kumar-2026" };

const T = {
  en: {
    switch: "EN", mobile: "Mobile number", password: "Password", signIn: "Sign in", createOwner: "Create account",
    yourName: "Your name", nameEn: "Name in English", aadhaar: "Aadhaar number", address: "Address",
    consent: "I explained to the borrower", save: "Save", giveLoan: "Give loan", loanAmount: "Loan amount",
    fixedToggle: "Borrower wants a fixed amount every month", fixedAmount: "Amount every month", next: "Next",
    saveLoan: "Save loan", openLoan: "Open the loan", recordPayment: "Record payment",
    amountReceived: "Amount received", savePayment: "Save payment", interest: "Interest", principal: "Principal",
    overdueTab: "Overdue", daysLate: "10 days late", collapse: "Collapse menu", expand: "Expand menu",
    vehicle: "Vehicle", reg: "Registration no.", price: "On-road price", down: "Down payment", addCharge: "Add a charge",
    partPayment: "Part payment", amountReceivedPart: "Amount received", finishSooner: "Finish sooner",
    addFee: "Add a charge", feesTitle: "Charges after the loan was given", rescheduled: "Rescheduled",
    amount: "Amount", ltvAck: "I still want to give this loan", handedOver: "Handed over on the day",
  },
  ta: {
    switch: "தமிழ்", mobile: "கைபேசி எண்", password: "கடவுச்சொல்", signIn: "உள்நுழை", createOwner: "கணக்கை உருவாக்கு",
    yourName: "உங்கள் பெயர்", nameEn: "ஆங்கிலத்தில் பெயர்", aadhaar: "ஆதார் எண்", address: "முகவரி",
    consent: "விவரங்கள் ஏன்", save: "சேமி", giveLoan: "கடன் கொடு", loanAmount: "கடன் தொகை",
    fixedToggle: "ஒவ்வொரு மாதமும் ஒரே தொகை கட்ட வாடிக்கையாளர் விரும்புகிறார்", fixedAmount: "ஒவ்வொரு மாதமும் தொகை",
    next: "அடுத்து", saveLoan: "கடனைச் சேமி", openLoan: "கடனைத் திற", recordPayment: "பணம் பதிவு",
    amountReceived: "பெற்ற தொகை", savePayment: "கட்டணத்தைச் சேமி", interest: "வட்டி", principal: "அசல்",
    overdueTab: "தவறியவை", daysLate: "10 நாள் தாமதம்", collapse: "மெனுவைச் சுருக்கு", expand: "மெனுவை விரி",
    vehicle: "வாகனம்", reg: "பதிவு எண்", price: "ஆன்-ரோடு விலை", down: "முன்பணம்", addCharge: "கட்டணம் சேர்",
    partPayment: "பகுதி செலுத்தல்", amountReceivedPart: "பெற்ற தொகை", finishSooner: "சீக்கிரம் முடியும்",
    addFee: "கட்டணம் சேர்", feesTitle: "கடனுக்குப் பிறகு கட்டணங்கள்", rescheduled: "மாற்றியமைக்கப்பட்டது",
    amount: "தொகை", ltvAck: "இருந்தாலும் இந்தக் கடனைக் கொடுக்கிறேன்", handedOver: "அன்று கையில் கொடுத்தது",
  },
} as const;

const D = [[0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],[3,4,0,1,2,8,9,5,6,7],
  [4,0,1,2,3,9,5,6,7,8],[5,9,8,7,6,0,4,3,2,1],[6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],
  [9,8,7,6,5,4,3,2,1,0]];
const P = [[0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],[8,9,1,6,0,4,3,5,2,7],
  [9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],[2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]];
const INV = [0,4,3,2,1,5,6,7,8,9];
function aadhaar(body11: string): string {
  let c = 0;
  body11.split("").reverse().forEach((ch, i) => { c = D[c][P[(i + 1) % 8][Number(ch)]]; });
  return body11 + INV[c];
}
const unique = () => String(Date.now()).slice(-8);

async function noOverflowOrRawKeys(page: Page) {
  const { width, view } = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, view: innerWidth }));
  expect(width, "no sideways scrolling").toBeLessThanOrEqual(view + 1);
  const text = await page.locator("body").innerText();
  expect(text).not.toMatch(/\b(app|nav|loan|borrower|dues|home|errors|settings|payment|status)\.[a-zA-Z_]+\b/);
}

async function signIn(page: Page, lang: "en" | "ta") {
  const t = T[lang];
  await page.goto("/login");
  await page.getByRole("button", { name: t.switch, exact: true }).click();
  const setup = await (await page.request.get("/api/v1/auth/setup")).json();
  if (setup.needs_setup) {
    await page.getByLabel(t.yourName, { exact: true }).fill(OWNER.name);
  }
  await page.getByLabel(t.mobile, { exact: true }).fill(OWNER.phone);
  await page.getByLabel(t.password, { exact: true }).fill(OWNER.password);
  await page.getByRole("button", { name: setup.needs_setup ? t.createOwner : t.signIn, exact: true }).click();
  await page.waitForURL("/");
  await page.getByRole("button", { name: t.switch, exact: true }).first().click();
}

for (const lang of ["en", "ta"] as const) {
  test(`borrower, fixed-amount loan and payment (${lang})`, async ({ page }) => {
    const t = T[lang];
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    await signIn(page, lang);
    await noOverflowOrRawKeys(page);

    const id = unique();
    await page.goto("/borrowers/new");
    await page.getByLabel(t.nameEn, { exact: true }).fill(`E2E Person ${id}`);
    await page.getByLabel(t.mobile, { exact: true }).fill(`9${id.padStart(9, "1")}`);
    await page.getByLabel(t.aadhaar, { exact: true }).fill(aadhaar(`5${id.padStart(10, "3")}`));
    await page.getByLabel(t.address, { exact: true }).fill("1, Test Street");
    await page.getByText(t.consent).click();
    await noOverflowOrRawKeys(page);
    await page.locator("form button[type=submit]").last().click();
    await page.waitForURL(/\/borrowers\/[0-9a-f-]{36}$/);
    await noOverflowOrRawKeys(page);

    await page.getByRole("button", { name: t.giveLoan, exact: true }).first().click();
    await page.getByRole("button", { name: t.next }).click(); // no security for this loan
    await page.getByLabel(t.loanAmount, { exact: true }).fill("50000");
    await page.getByText(t.fixedToggle, { exact: true }).click();
    await page.getByLabel(t.fixedAmount, { exact: true }).fill("5000");
    const preview = page.locator('section[aria-live="polite"]');
    await expect(preview).toContainText("₹5,000.00");
    await expect(preview).toContainText("13");
    await expect(preview).toContainText("₹63,000.00");
    await noOverflowOrRawKeys(page);
    await page.getByRole("button", { name: t.next }).click();
    await page.getByRole("button", { name: t.saveLoan, exact: true }).click();
    await page.getByRole("button", { name: t.openLoan, exact: true }).click();
    await page.waitForURL(/\/loans\/[0-9a-f-]{36}$/);
    await noOverflowOrRawKeys(page);

    await page.getByRole("button", { name: t.recordPayment, exact: true }).first().click();
    await page.getByLabel(t.amountReceived, { exact: true }).fill("5000");
    await page.getByRole("button", { name: t.savePayment, exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("₹1,000.00");
    await expect(dialog).toContainText("₹4,000.00");
    await expect(dialog).toContainText("₹58,000.00");
    expect(errors).toEqual([]);
  });

  test(`an installment 10 days late shows in Overdue (${lang})`, async ({ page }) => {
    const t = T[lang];
    await signIn(page, lang);
    const csrf = (await page.context().cookies()).find((c) => c.name === "lt_csrf")?.value ?? "";
    const headers = { "X-CSRF-Token": csrf };
    const id = unique();
    const b = await (await page.request.post("/api/v1/borrowers", { headers, data: {
      name_en: `Late Payer ${id}`, phone: `8${id.padStart(9, "2")}`, aadhaar: aadhaar(`6${id.padStart(10, "4")}`),
      address: "x", consent: { given: true } } })).json();
    const today = new Date(new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date()));
    const iso = (days: number) => new Date(today.getTime() - days * 86400000).toISOString().slice(0, 10);
    const loan = await (await page.request.post("/api/v1/loans", { headers, data: {
      borrower_id: b.id, idempotency_key: `e2e-late-${id}-${lang}`,
      terms: { principal: "10000", rate: "2", term_value: 6, disbursal_date: iso(40), first_due_date: iso(10) } } })).json();
    await page.goto("/");
    await page.getByRole("tab", { name: new RegExp(`^${t.overdueTab}`) }).click();
    const row = page.locator("article").filter({ hasText: loan.loan_no });
    await expect(row).toContainText(t.daysLate);
    await noOverflowOrRawKeys(page);
  });

  test(`the left menu and the page fit the screen (${lang})`, async ({ page }, testInfo) => {
    const t = T[lang];
    await signIn(page, lang);
    const aside = page.locator("aside[data-sidebar]");
    const bottom = page.locator("nav[data-bottom-nav]");
    // The menu and the page share the full width: no gap, no overlap, no sideways scrolling.
    const shared = () => page.evaluate(() => {
      const a = document.querySelector("aside[data-sidebar]")!.getBoundingClientRect();
      const m = document.querySelector("main")!.getBoundingClientRect();
      return { aside: Math.round(a.width), main: Math.round(m.width), touching: Math.abs(m.left - a.right) <= 1,
        total: Math.round(a.width + m.width), screen: document.documentElement.clientWidth };
    });
    const allLinksVisible = async () => {
      for (const link of await aside.locator("nav a").all()) await expect(link).toBeInViewport();
    };

    if (testInfo.project.name === "phone") {
      await expect(bottom).toBeVisible();
      await expect(aside).toBeHidden();
      return;
    }
    await expect(bottom).toBeHidden();
    await expect(aside).toBeVisible();
    await allLinksVisible();

    if (testInfo.project.name === "tablet") {
      // Tablets get the narrow rail with short labels; there is nothing to fold.
      await expect(aside).toHaveAttribute("data-sidebar", "rail");
      await expect(page.getByRole("button", { name: t.collapse })).toHaveCount(0);
    } else {
      await expect(aside).toHaveAttribute("data-sidebar", "full");
      const full = await shared();
      expect(full.touching).toBe(true);
      expect(Math.abs(full.total - full.screen)).toBeLessThanOrEqual(2);

      // Folding the menu gives the page the space, and the choice survives a reload.
      await page.getByRole("button", { name: t.collapse }).click();
      await expect(aside).toHaveAttribute("data-sidebar", "rail");
      await expect.poll(async () => (await shared()).main).toBeGreaterThan(full.main + 80);
      await allLinksVisible();
      await page.goto("/loans");
      await noOverflowOrRawKeys(page);
      await page.reload();
      await expect(aside).toHaveAttribute("data-sidebar", "rail");
      await page.getByRole("button", { name: t.expand }).click();
      await expect(aside).toHaveAttribute("data-sidebar", "full");
    }
    const after = await shared();
    expect(after.touching).toBe(true);
    expect(Math.abs(after.total - after.screen)).toBeLessThanOrEqual(2);
    await noOverflowOrRawKeys(page);
  });

  test(`vehicle loan: down payment, a charge taken out, loan-to-value check (${lang})`, async ({ page }) => {
    const t = T[lang];
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    await signIn(page, lang);
    const csrf = (await page.context().cookies()).find((c) => c.name === "lt_csrf")?.value ?? "";
    const id = unique();
    const b = await (await page.request.post("/api/v1/borrowers", { headers: { "X-CSRF-Token": csrf }, data: {
      name_en: `Vehicle Buyer ${id}`, phone: `7${id.padStart(9, "3")}`, aadhaar: aadhaar(`7${id.padStart(10, "5")}`),
      address: "x", consent: { given: true } } })).json();
    await page.goto(`/loans/new?borrower=${b.id}`);

    // Security: a new vehicle at 1,20,000 with 20,000 down; the loan amount becomes 1,00,000.
    await page.getByText(t.vehicle, { exact: true }).first().click();
    await page.getByLabel(t.reg).fill("TN 59 AB 1234"); // optional fields are labelled "… (optional)"
    await page.getByLabel(t.price, { exact: true }).fill("120000");
    await page.getByLabel(t.down).fill("20000");
    await noOverflowOrRawKeys(page);
    await page.getByRole("button", { name: t.next }).click();
    await expect(page.getByLabel(t.loanAmount, { exact: true })).toHaveValue("1,00,000");

    // A 2,000 processing fee taken out: 98,000 is handed over; 1,00,000 on a 1,20,000 vehicle is 83.33 %.
    await page.getByRole("button", { name: t.addCharge }).click();
    await page.getByLabel(t.amount, { exact: true }).last().fill("2000");
    const preview = page.locator('section[aria-live="polite"]');
    await expect(preview).toContainText("₹98,000.00");
    await expect(preview).toContainText("83.33%");
    await noOverflowOrRawKeys(page);
    await page.getByRole("button", { name: t.next }).click();

    const save = page.getByRole("button", { name: t.saveLoan, exact: true });
    await expect(save).toBeDisabled(); // above the 75 % limit until confirmed
    await page.getByText(t.ltvAck).click();
    await save.click();
    await page.getByRole("button", { name: t.openLoan, exact: true }).click();
    await page.waitForURL(/\/loans\/[0-9a-f-]{36}$/);
    await expect(page.locator("main")).toContainText("TN 59 AB 1234");
    await expect(page.locator("main")).toContainText(t.handedOver);
    await expect(page.locator("main")).toContainText("₹98,000.00");
    await noOverflowOrRawKeys(page);
    expect(errors).toEqual([]);
  });

  test(`part payment to finish sooner, then a bounce charge (${lang})`, async ({ page }) => {
    const t = T[lang];
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    await signIn(page, lang);
    const csrf = (await page.context().cookies()).find((c) => c.name === "lt_csrf")?.value ?? "";
    const headers = { "X-CSRF-Token": csrf };
    const id = unique();
    const b = await (await page.request.post("/api/v1/borrowers", { headers, data: {
      name_en: `Part Payer ${id}`, phone: `6${id.padStart(9, "4")}`, aadhaar: aadhaar(`8${id.padStart(10, "6")}`),
      address: "x", consent: { given: true } } })).json();
    const today = new Date(new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date()));
    const given = new Date(today.getTime() - 5 * 86400000).toISOString().slice(0, 10);
    const loan = await (await page.request.post("/api/v1/loans", { headers, data: {
      borrower_id: b.id, idempotency_key: `e2e-part-${id}-${lang}`,
      terms: { principal: "100000", rate: "2", term_value: 12, disbursal_date: given } } })).json();
    await page.goto(`/loans/${loan.id}`);

    await page.getByRole("button", { name: t.partPayment, exact: true }).click();
    const sheet = page.getByRole("dialog");
    await sheet.getByLabel(t.amountReceivedPart).fill("30000");
    await sheet.getByText(t.finishSooner).click();
    await expect(sheet).toContainText("₹70,000.00"); // principal after: 1,00,000 − 30,000
    await expect(sheet).toContainText("12 → ");
    await noOverflowOrRawKeys(page);
    await sheet.getByRole("button").last().click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.locator("main")).toContainText(t.rescheduled);

    await page.getByRole("button", { name: t.addFee, exact: true }).first().click();
    await page.getByRole("dialog").getByRole("button").last().click();
    await expect(page.locator("main")).toContainText(t.feesTitle);
    await expect(page.locator("main")).toContainText("₹500.00");
    await noOverflowOrRawKeys(page);
    expect(errors).toEqual([]);
  });
}
