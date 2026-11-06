import { Languages } from "lucide-react";
import { useTranslation } from "react-i18next";

import { englishToTamil, hasTamil, tamilToEnglish } from "@/lib/translit";

import { Field, Input } from "./ui/field";

interface Props {
  nameEn: string;
  nameTa: string;
  onChange: (next: { nameEn: string; nameTa: string }) => void;
  error?: string;
  labelEn?: string;
  labelTa?: string;
}

/** English and Tamil name fields; each suggests a spelling for the other (offline, editable). */
export function NameFields({ nameEn, nameTa, onChange, error, labelEn, labelTa }: Props) {
  const { t } = useTranslation();
  const taSuggestion = nameEn && !nameTa && !hasTamil(nameEn) ? englishToTamil(nameEn) : "";
  const enSuggestion = nameTa && !nameEn && hasTamil(nameTa) ? tamilToEnglish(nameTa) : "";
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Field label={labelEn ?? t("borrower.nameEn")} error={error} hint={t("borrower.nameRule")}>
        {(id, d) => (
          <>
            <Input id={id} aria-describedby={d} value={nameEn} autoComplete="off" lang="en"
              onChange={(e) => onChange({ nameEn: e.target.value, nameTa })} />
            {enSuggestion && (
              <Suggestion text={t("borrower.suggestEn", { text: enSuggestion })}
                onUse={() => onChange({ nameEn: enSuggestion, nameTa })} />
            )}
          </>
        )}
      </Field>
      <Field label={labelTa ?? t("borrower.nameTa")}>
        {(id, d) => (
          <>
            <Input id={id} aria-describedby={d} value={nameTa} autoComplete="off" lang="ta"
              onChange={(e) => onChange({ nameEn, nameTa: e.target.value })} />
            {taSuggestion && (
              <Suggestion text={t("borrower.suggestTa", { text: taSuggestion })}
                onUse={() => onChange({ nameEn, nameTa: taSuggestion })} />
            )}
          </>
        )}
      </Field>
    </div>
  );
}

function Suggestion({ text, onUse }: { text: string; onUse: () => void }) {
  const { t } = useTranslation();
  return (
    <button type="button" onClick={onUse}
      className="mt-2 inline-flex min-h-touch items-center gap-2 rounded-full bg-brand-soft px-4 text-left text-sm font-semibold text-brand">
      <Languages className="h-4 w-4 shrink-0" aria-hidden />
      <span>{text}</span>
      <span className="font-semibold underline">{t("borrower.useSuggestion")}</span>
    </button>
  );
}
