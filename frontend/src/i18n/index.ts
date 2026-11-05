import i18n from "i18next";
import { initReactI18next, useTranslation } from "react-i18next";

import { ApiError } from "@/api/client";
import type { Lang } from "@/lib/format";

import en from "./en.json";

// Adding a language means adding a JSON file here and to the switcher; nothing else changes.
export const LANGUAGES: { code: Lang; label: string }[] = [
  { code: "en", label: "EN" },
  { code: "ta", label: "தமிழ்" },
];

const stored = (() => {
  try {
    return localStorage.getItem("lt-lang");
  } catch {
    return null;
  }
})();

// English is bundled (it is also the fallback); Tamil is a separate chunk loaded on demand, so
// the first screen parses one language, not two.
export async function loadLanguage(lang: string): Promise<void> {
  if (lang === "ta" && !i18n.hasResourceBundle("ta", "translation")) {
    const ta = await import("./ta.json");
    i18n.addResourceBundle("ta", "translation", ta.default, true, true);
  }
}

const initial = stored === "ta" ? "ta" : "en";
void i18n.use(initReactI18next).init({
  resources: { en: { translation: en } },
  lng: "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
  returnNull: false,
});

/** Resolves once the saved language is loaded, so the first paint is already in that language. */
export const i18nReady: Promise<unknown> =
  initial === "ta" ? loadLanguage("ta").then(() => i18n.changeLanguage("ta")) : Promise.resolve();

/** Change language (loads the file first if needed). */
export async function setLanguage(lang: string): Promise<void> {
  await loadLanguage(lang);
  await i18n.changeLanguage(lang);
}

function applyLang(lang: string): void {
  document.documentElement.lang = lang;
}
applyLang(i18n.language);
i18n.on("languageChanged", (lang) => {
  applyLang(lang);
  try {
    localStorage.setItem("lt-lang", lang);
  } catch {
    /* private mode */
  }
});

export function useLang(): Lang {
  const { i18n: inst } = useTranslation();
  return (inst.language === "ta" ? "ta" : "en") as Lang;
}

/** Turn any thrown error into a message in the current language (PRD section 9). */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const key = `errors.${err.code}`;
    if (i18n.exists(key)) return i18n.t(key, err.params as Record<string, string>);
    return i18n.t("errors.unknown", { code: err.code });
  }
  return i18n.t("errors.NETWORK_ERROR");
}

export default i18n;
