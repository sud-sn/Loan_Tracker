import { describe, expect, it } from "vitest";

import { amountInWords, dmy, groupWhileTyping, longDate, money, parseMoney } from "./format";
import { englishToTamil, tamilToEnglish } from "./translit";
import { isValidAadhaar, isValidPhone } from "./verhoeff";

describe("money", () => {
  it("uses Indian grouping in both languages", () => {
    expect(money("100000")).toBe("₹1,00,000.00");
    expect(money("12345678.5")).toBe("₹1,23,45,678.50");
    expect(money(-2500)).toBe("-₹2,500.00");
  });
  it("groups while typing and parses back", () => {
    expect(groupWhileTyping("100000")).toBe("1,00,000");
    expect(groupWhileTyping("1250.5")).toBe("1,250.5");
    expect(groupWhileTyping("12.345")).toBe("12.34");
    expect(parseMoney("1,00,000.50")).toBe("100000.50");
    expect(parseMoney("abc")).toBe("");
  });
});

describe("amount in words", () => {
  it("English, Indian system", () => {
    expect(amountInWords("100000", "en")).toBe("One lakh rupees only");
    expect(amountInWords("9455.96", "en")).toBe("Nine thousand four hundred fifty-five rupees and ninety-six paise only");
    expect(amountInWords("10500000", "en")).toBe("One crore five lakh rupees only");
  });
  it("Tamil", () => {
    expect(amountInWords("100000", "ta")).toBe("ஒரு லட்சம் ரூபாய்");
    expect(amountInWords("2500", "ta")).toBe("இரண்டு ஆயிரத்து ஐந்நூறு ரூபாய்");
    expect(amountInWords("125000.50", "ta")).toBe("ஒரு லட்சத்து இருபத்து ஐந்து ஆயிரம் ரூபாய் ஐம்பது பைசா");
  });
  it("matches the server's wording", () => {
    // Same output as app/core/i18n.py so the screen and the printed receipt agree.
    expect(amountInWords("1", "en")).toBe("One rupee only");
    expect(amountInWords("1", "ta")).toBe("ஒரு ரூபாய்");
  });
});

describe("dates", () => {
  it("DD/MM/YYYY and localised month names", () => {
    expect(dmy("2026-11-04")).toBe("04/11/2026");
    expect(longDate("2026-11-04", "en")).toBe("Wednesday, 04 November 2026");
    expect(longDate("2026-11-04", "ta")).toBe("புதன், 04 நவம்பர் 2026");
  });
});

describe("transliteration suggestions", () => {
  it("English to Tamil", () => {
    expect(englishToTamil("Murugan")).toBe("முருகன்");
    expect(englishToTamil("Selvi")).toBe("செல்வி");
    expect(englishToTamil("Kannan")).toBe("கன்னன்");
    expect(englishToTamil("Lakshmi")).toBe("லக்ஷ்மி");
    expect(englishToTamil("Senthil")).toBe("செந்தில்");
    expect(englishToTamil("Pandian")).toBe("பண்டியன்");
  });
  it("Tamil to English", () => {
    expect(tamilToEnglish("முருகன்")).toBe("Murugan");
    expect(tamilToEnglish("செல்வி")).toBe("Selvi");
  });
});

describe("validation", () => {
  it("Verhoeff for Aadhaar", () => {
    expect(isValidAadhaar("234123412346")).toBe(true);
    expect(isValidAadhaar("234123412345")).toBe(false);
    expect(isValidAadhaar("123412341234")).toBe(false); // cannot start with 1
  });
  it("Indian mobile numbers", () => {
    expect(isValidPhone("9876543210")).toBe(true);
    expect(isValidPhone("+91 98765 43210")).toBe(true);
    expect(isValidPhone("5876543210")).toBe(false);
  });
});
