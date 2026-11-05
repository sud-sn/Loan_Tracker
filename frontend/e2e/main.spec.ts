import { expect, test, type Page } from "@playwright/test";

// Main flows at phone width in English and Tamil: sign in, add a borrower, give a fixed-amount
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
    overdueTab: "Overdue", daysLate: "10 days late",
  },
  ta: {
    switch: "தமிழ்", mobile: "கைபேசி எண்", password: "கடவுச்சொல்", signIn: "உள்நுழை", createOwner: "கணக்கை உருவாக்கு",
    yourName: "உங்கள் பெயர்", nameEn: "ஆங்கிலத்தில் பெயர்", aadhaar: "ஆதார் எண்", address: "முகவரி",
    consent: "விவரங்கள் ஏன்", save: "சேமி", giveLoan: "கடன் கொடு", loanAmount: "கடன் தொகை",
    fixedToggle: "ஒவ்வொரு மாதமும் ஒரே தொகை கட்ட வாடிக்கையாளர் விரும்புகிறார்", fixedAmount: "ஒவ்வொரு மாதமும் தொகை",
    next: "அடுத்து", saveLoan: "கடனைச் சேமி", openLoan: "கடனைத் திற", recordPayment: "பணம் பதிவு",
    amountReceived: "பெற்ற தொகை", savePayment: "கட்டணத்தைச் சேமி", interest: "வட்டி", principal: "அசல்",
    overdueTab: "தவறியவை", daysLate: "10 நாள் தாமதம்",
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
  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(width, "no sideways scrolling at 360 px").toBeLessThanOrEqual(361);
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
}
