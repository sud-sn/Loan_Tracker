import i18n from "i18next";
import { initReactI18next, useTranslation } from "react-i18next";

import { ApiError } from "@/api/client";
import type { Lang } from "@/lib/format";

import en from "./en.json";
import ta from "./ta.json";

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

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ta: { translation: ta } },
  lng: stored === "ta" ? "ta" : "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
  returnNull: false,
});

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
