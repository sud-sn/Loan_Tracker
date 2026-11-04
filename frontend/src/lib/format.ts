/** Money, dates and amounts in words. Indian grouping in both languages; Western digits always. */

export type Lang = "en" | "ta";

const groupFormatter = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const wholeFormatter = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

/** "100000.5" → "₹1,00,000.50" */
export function money(value: string | number | null | undefined, symbol = true): string {
  if (value === null || value === undefined || value === "") return "";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return String(value);
  const text = groupFormatter.format(Math.abs(n));
  return `${n < 0 ? "-" : ""}${symbol ? "₹" : ""}${text}`;
}

/** Format a money input while typing: keeps what the user typed, adds Indian grouping. */
export function groupWhileTyping(raw: string): string {
  const cleaned = raw.replace(/[^\d.]/g, "");
  const [whole = "", ...rest] = cleaned.split(".");
  const frac = rest.join("").slice(0, 2);
  const grouped = whole ? wholeFormatter.format(Number(whole.replace(/^0+(?=\d)/, ""))) : "";
  return cleaned.includes(".") ? `${grouped || "0"}.${frac}` : grouped;
}

/** "1,00,000.50" → "100000.50" (or "" when empty / invalid). */
export function parseMoney(display: string): string {
  const cleaned = display.replace(/,/g, "").trim();
  if (!cleaned) return "";
  if (!/^\d+(\.\d{0,2})?$/.test(cleaned)) return "";
  return cleaned.endsWith(".") ? cleaned.slice(0, -1) : cleaned;
}

export function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Today's date in IST, as YYYY-MM-DD. */
export function todayIST(): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit",
    day: "2-digit" }).format(new Date());
  return parts;
}

export function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d + days));
  return date.toISOString().slice(0, 10);
}

/** "2026-11-04" → "04/11/2026" */
export function dmy(iso: string | null | undefined): string {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

const MONTHS: Record<Lang, string[]> = {
  en: ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
    "November", "December"],
  ta: ["ஜனவரி", "பிப்ரவரி", "மார்ச்", "ஏப்ரல்", "மே", "ஜூன்", "ஜூலை", "ஆகஸ்ட்", "செப்டம்பர்", "அக்டோபர்", "நவம்பர்",
    "டிசம்பர்"],
};
const WEEKDAYS: Record<Lang, string[]> = {
  en: ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
  ta: ["ஞாயிறு", "திங்கள்", "செவ்வாய்", "புதன்", "வியாழன்", "வெள்ளி", "சனி"],
};

/** "2026-11-04" → "Wednesday, 04 November 2026" / "புதன், 04 நவம்பர் 2026" */
export function longDate(iso: string, lang: Lang): string {
  const [y, m, d] = iso.split("-").map(Number);
  const weekday = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  return `${WEEKDAYS[lang][weekday]}, ${String(d).padStart(2, "0")} ${MONTHS[lang][m - 1]} ${y}`;
}

export function displayName(lang: Lang, nameEn?: string | null, nameTa?: string | null): string {
  return (lang === "ta" ? nameTa || nameEn : nameEn || nameTa) || "";
}

// ------------------------------------------------------------------ amounts in words

const EN_ONES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
  "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"];
const EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"];

function enBelow1000(n: number): string {
  const words: string[] = [];
  if (n >= 100) {
    words.push(`${EN_ONES[Math.floor(n / 100)]} hundred`);
    n %= 100;
  }
  if (n >= 20) words.push(EN_TENS[Math.floor(n / 10)] + (n % 10 ? `-${EN_ONES[n % 10]}` : ""));
  else if (n) words.push(EN_ONES[n]);
  return words.join(" ");
}

function enWords(n: number): string {
  if (n === 0) return "zero";
  const parts: string[] = [];
  const units: [number, string][] = [[1e7, "crore"], [1e5, "lakh"], [1e3, "thousand"]];
  for (const [div, label] of units) {
    if (n >= div) {
      const count = Math.floor(n / div);
      parts.push(`${div === 1e7 ? enWords(count) : enBelow1000(count)} ${label}`);
      n %= div;
    }
  }
  if (n) parts.push(enBelow1000(n));
  return parts.join(" ");
}

const TA_ONES = ["", "ஒன்று", "இரண்டு", "மூன்று", "நான்கு", "ஐந்து", "ஆறு", "ஏழு", "எட்டு", "ஒன்பது"];
const TA_TEENS = ["பத்து", "பதினொன்று", "பன்னிரண்டு", "பதின்மூன்று", "பதினான்கு", "பதினைந்து", "பதினாறு", "பதினேழு",
  "பதினெட்டு", "பத்தொன்பது"];
const TA_TENS = ["", "", "இருபது", "முப்பது", "நாற்பது", "ஐம்பது", "அறுபது", "எழுபது", "எண்பது", "தொண்ணூறு"];
const TA_TENS_JOIN = ["", "", "இருபத்து", "முப்பத்து", "நாற்பத்து", "ஐம்பத்து", "அறுபத்து", "எழுபத்து", "எண்பத்து",
  "தொண்ணூற்று"];
const TA_HUNDREDS = ["", "நூறு", "இருநூறு", "முந்நூறு", "நானூறு", "ஐந்நூறு", "அறுநூறு", "எழுநூறு", "எண்ணூறு",
  "தொள்ளாயிரம்"];
const TA_HUNDREDS_JOIN = ["", "நூற்று", "இருநூற்று", "முந்நூற்று", "நானூற்று", "ஐந்நூற்று", "அறுநூற்று", "எழுநூற்று",
  "எண்ணூற்று", "தொள்ளாயிரத்து"];

function taBelow100(n: number): string {
  if (n < 10) return TA_ONES[n];
  if (n < 20) return TA_TEENS[n - 10];
  const tens = Math.floor(n / 10);
  const ones = n % 10;
  return ones ? `${TA_TENS_JOIN[tens]} ${TA_ONES[ones]}` : TA_TENS[tens];
}

function taBelow1000(n: number): string {
  const hundreds = Math.floor(n / 100);
  const rest = n % 100;
  if (!hundreds) return taBelow100(rest);
  if (!rest) return TA_HUNDREDS[hundreds];
  return `${TA_HUNDREDS_JOIN[hundreds]} ${taBelow100(rest)}`;
}

function taWords(n: number): string {
  if (n === 0) return "பூஜ்ஜியம்";
  const parts: string[] = [];
  const units: [number, string, string][] = [[1e7, "கோடி", "கோடியே"], [1e5, "லட்சம்", "லட்சத்து"],
    [1e3, "ஆயிரம்", "ஆயிரத்து"]];
  for (const [div, last, joined] of units) {
    if (n >= div) {
      const count = Math.floor(n / div);
      n %= div;
      parts.push(`${count === 1 ? "ஒரு" : taWords(count)} ${n ? joined : last}`);
    }
  }
  if (n) parts.push(taBelow1000(n));
  return parts.join(" ");
}

/** Shown under every money field to catch an extra zero (PRD section 10). */
export function amountInWords(value: string, lang: Lang): string {
  if (!value || !/^\d+(\.\d+)?$/.test(value)) return "";
  const [wholeText, fracText = ""] = value.split(".");
  const rupees = Number(wholeText);
  const paise = Number((fracText + "00").slice(0, 2));
  if (!Number.isSafeInteger(rupees)) return "";
  if (lang === "ta") {
    let text = `${rupees === 1 ? "ஒரு" : taWords(rupees)} ரூபாய்`;
    if (paise) text += ` ${taWords(paise)} பைசா`;
    return text;
  }
  let text = `${enWords(rupees)} ${rupees === 1 ? "rupee" : "rupees"}`;
  if (paise) text += ` and ${enWords(paise)} paise`;
  return text.charAt(0).toUpperCase() + text.slice(1) + " only";
}
