/**
 * Offline English ↔ Tamil name suggestions (PRD section 9). Nothing is sent over the internet.
 *
 * English → Tamil uses a phonetic scheme close to how names are usually spelt in Tamil Nadu
 * ("Murugan" → முருகன், "Lakshmi" → லக்ஷ்மி). Tamil → English is a plain romanisation. Both are
 * suggestions only; the lender can always edit them.
 */

const VOWELS: [string, string, string][] = [
  // latin, independent vowel, vowel sign
  ["aa", "ஆ", "ா"], ["ii", "ஈ", "ீ"], ["ee", "ஈ", "ீ"], ["uu", "ஊ", "ூ"], ["oo", "ஊ", "ூ"], ["ai", "ஐ", "ை"],
  ["au", "ஔ", "ௌ"], ["ou", "ஔ", "ௌ"], ["a", "அ", ""], ["i", "இ", "ி"], ["u", "உ", "ு"], ["e", "எ", "ெ"],
  ["o", "ஒ", "ொ"], ["y", "இ", "ி"],
];

const CONSONANTS: [string, string][] = [
  ["ksh", "க்ஷ"], ["shr", "ஷ்ர"], ["sri", "ஸ்ரீ"], ["ng", "ங"], ["nj", "ஞ"], ["ch", "ச"], ["sh", "ஷ"], ["th", "த"],
  ["dh", "த"], ["zh", "ழ"], ["ph", "ப"], ["bh", "ப"], ["kh", "க"], ["gh", "க"], ["k", "க"], ["g", "க"], ["c", "க"],
  ["q", "க"], ["s", "ச"], ["j", "ஜ"], ["t", "ட"], ["d", "ட"], ["n", "ன"], ["p", "ப"], ["b", "ப"], ["f", "ப"],
  ["m", "ம"], ["y", "ய"], ["r", "ர"], ["l", "ல"], ["v", "வ"], ["w", "வ"], ["h", "ஹ"], ["z", "ஸ"], ["x", "க்ஸ"],
];
const VIRAMA = "்";

function startsWithAt(text: string, i: number, token: string): boolean {
  return text.startsWith(token, i);
}

function matchVowel(word: string, i: number): [string, string, number] | null {
  for (const [latin, independent, sign] of VOWELS) {
    if (latin === "y") continue;
    if (startsWithAt(word, i, latin)) return [independent, sign, latin.length];
  }
  return null;
}

function wordToTamil(word: string): string {
  let out = "";
  let i = 0;
  const lower = word.toLowerCase();
  if (lower === "sri" || lower === "shri") return "ஸ்ரீ";
  let prevVowel = "";
  while (i < lower.length) {
    const vowel = matchVowel(lower, i);
    if (vowel) {
      if (prevVowel) {
        // Two vowels in a row take a glide, as names are written: Pandian → பண்டியன், Ruvan → ருவன்.
        const glide = /^(i|ii|ee|e|ai|y)$/.test(prevVowel) ? "ய" : "வ";
        out += glide + vowel[1];
      } else {
        out += vowel[0];
      }
      prevVowel = lower.slice(i, i + vowel[2]);
      i += vowel[2];
      continue;
    }
    prevVowel = "";
    let matched: [string, string] | undefined;
    for (const pair of CONSONANTS) {
      if (startsWithAt(lower, i, pair[0])) {
        matched = pair;
        break;
      }
    }
    if (!matched) {
      out += word[i];
      i += 1;
      continue;
    }
    const latin = matched[0];
    let tamil = matched[1];
    // "n" at the start of a word or before d/t is ந / ண; otherwise ன.
    if (latin === "n") {
      if (i === 0) tamil = "ந";
      // Before "th"/"dh" (த) it is the dental ந (Senthil → செந்தில்); before a plain t/d (ட) it is ண.
      else if (lower.startsWith("th", i + 1) || lower.startsWith("dh", i + 1)) tamil = "ந";
      else if (lower[i + 1] === "d" || lower[i + 1] === "t") tamil = "ண";
    }
    // A single "s" at the start is usually ச (Selvi, Senthil); "sw/sv" → ஸ.
    if (latin === "s" && (lower[i + 1] === "w" || lower[i + 1] === "v")) tamil = "ஸ";
    i += latin.length;
    const next = matchVowel(lower, i);
    const yVowel = lower[i] === "y" && (i + 1 === lower.length || !matchVowel(lower, i + 1));
    if (next) {
      out += tamil + next[1];
      prevVowel = lower.slice(i, i + next[2]);
      i += next[2];
    } else if (yVowel) {
      out += tamil + "ி";
      prevVowel = "i";
      i += 1;
    } else {
      out += tamil + VIRAMA;
    }
  }
  return out;
}

export function englishToTamil(text: string): string {
  return text
    .split(/(\s+|\.)/)
    .map((part) => (/^[A-Za-z]+$/.test(part) ? wordToTamil(part) : part))
    .join("");
}

const T_VOWELS: Record<string, string> = {
  அ: "a", ஆ: "aa", இ: "i", ஈ: "ee", உ: "u", ஊ: "oo", எ: "e", ஏ: "e", ஐ: "ai", ஒ: "o", ஓ: "o", ஔ: "au",
};
const T_CONS: Record<string, string> = {
  க: "k", ங: "ng", ச: "s", ஞ: "nj", ட: "d", ண: "n", த: "th", ந: "n", ப: "p", ம: "m", ய: "y", ர: "r", ல: "l",
  வ: "v", ழ: "zh", ள: "l", ற: "r", ன: "n", ஜ: "j", ஷ: "sh", ஸ: "s", ஹ: "h",
};
const T_SIGNS: Record<string, string> = {
  "ா": "a", "ி": "i", "ீ": "ee", "ு": "u", "ூ": "oo", "ெ": "e", "ே": "e", "ை": "ai", "ொ": "o", "ோ": "o", "ௌ": "au",
};

export function tamilToEnglish(text: string): string {
  const chars = Array.from(text.normalize("NFC"));
  let out = "";
  for (let i = 0; i < chars.length; i++) {
    const ch = chars[i];
    if (T_CONS[ch] !== undefined) {
      const next = chars[i + 1];
      let base = T_CONS[ch];
      // Soft sounds between vowels read better in names: முருகன் → Murugan, not Murukan.
      const prev = out.slice(-1);
      if (ch === "க" && /[aeiou]/.test(prev) && next !== VIRAMA) base = "g";
      if (ch === "ட" && /[aeiou]/.test(prev) && next !== VIRAMA) base = "d";
      if (ch === "ப" && /[aeiou]/.test(prev) && next !== VIRAMA) base = "b";
      if (next === VIRAMA) {
        out += base;
        i += 1;
      } else if (next && T_SIGNS[next] !== undefined) {
        out += base + T_SIGNS[next];
        i += 1;
      } else {
        out += base + "a";
      }
    } else if (T_VOWELS[ch] !== undefined) {
      out += T_VOWELS[ch];
    } else if (T_SIGNS[ch] === undefined && ch !== VIRAMA) {
      out += ch;
    }
  }
  return out.replace(/(^|\s)([a-z])/g, (_, space: string, letter: string) => space + letter.toUpperCase());
}

export function hasTamil(text: string): boolean {
  return /[஀-௿]/.test(text);
}
