import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { LANGUAGES } from "@/i18n";
import { cn } from "@/lib/utils";

/** EN | தமிழ் — switches every screen at once, no reload; saved to the user (PRD section 9). */
export function LanguageSwitch({ className }: { className?: string }) {
  const { i18n, t } = useTranslation();
  const { me } = useAuth();
  const qc = useQueryClient();
  const change = (code: string) => {
    void i18n.changeLanguage(code);
    if (me) {
      api.put("/auth/language", { language: code }).then(() => qc.invalidateQueries({ queryKey: ["me"] }))
        .catch(() => undefined);
    }
  };
  return (
    <div role="group" aria-label={t("app.language")}
      className={cn("inline-flex rounded-xl border border-line bg-surface p-0.5", className)}>
      {LANGUAGES.map((l) => (
        <button key={l.code} type="button" onClick={() => change(l.code)} aria-pressed={i18n.language === l.code}
          lang={l.code}
          className={cn("min-h-[44px] min-w-[52px] rounded-lg px-2 text-sm font-semibold",
            i18n.language === l.code ? "bg-brand text-brand-ink" : "text-ink hover:bg-sunken")}>
          {l.label}
        </button>
      ))}
    </div>
  );
}
