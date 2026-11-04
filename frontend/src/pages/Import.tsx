import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Download, FileSpreadsheet } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, api, openFile } from "@/api/client";
import type { ImportSummary } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, KeyValue } from "@/components/ui/states";
import { errorMessage, useLang } from "@/i18n";
import { displayName, dmy, money } from "@/lib/format";

export function ImportPage() {
  const { t, i18n } = useTranslation();
  const lang = useLang();
  const [file, setFile] = useState<File | null>(null);
  const send = (path: string) => {
    const form = new FormData();
    if (file) form.append("file", file);
    return api.upload<ImportSummary>(path, form);
  };
  const preview = useMutation({ mutationFn: () => send("/import/preview") });
  const commit = useMutation({ mutationFn: () => send("/import/commit") });
  const p = preview.data;
  const errLabel = (code: string) => (i18n.exists(`errors.${code}`) ? t(`errors.${code}`) : code);
  return (
    <div className="space-y-4">
      <h1 className="text-2xl">{t("import.title")}</h1>
      <p>{t("import.intro")}</p>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" onClick={() => void openFile("/import/template.xlsx", undefined, true)}>
          <Download className="h-5 w-5" aria-hidden />{t("import.template")}
        </Button>
        <label className="inline-flex min-h-touch cursor-pointer items-center gap-2 rounded-xl bg-brand-soft px-4 font-semibold text-brand">
          <FileSpreadsheet className="h-5 w-5" aria-hidden />{file ? file.name : t("import.upload")}
          <input type="file" accept=".xlsx,.csv" className="sr-only" onChange={(e) => {
            setFile(e.target.files?.[0] ?? null);
            preview.reset();
            commit.reset();
          }} />
        </label>
        <Button disabled={!file} loading={preview.isPending} onClick={() => preview.mutate()}>{t("import.preview")}</Button>
      </div>
      {preview.error && <p role="alert" className="field-error">{errorMessage(preview.error)}</p>}
      {p && (
        <>
          <Card>
            <h2 className="mb-1 text-lg">{t("import.totals")}</h2>
            <dl>
              <KeyValue label={t("import.loans")} value={p.loans} />
              <KeyValue label={t("import.borrowers")} value={p.borrowers} />
              <KeyValue label={t("import.payments")} value={p.payments} />
              <KeyValue label={t("import.principal")} value={money(p.total_principal)} />
              <KeyValue label={t("import.paid")} value={money(p.total_paid)} />
              <KeyValue label={t("import.outstanding")} value={money(p.total_outstanding)} strong />
            </dl>
            {p.missing_aadhaar > 0 && <p className="mt-2 text-due">{t("import.missingAadhaar", { count: p.missing_aadhaar })}</p>}
          </Card>
          {p.errors.length > 0 ? (
            <Card className="border-late/40">
              <h2 className="mb-2 text-lg text-late">{t("import.errors", { count: p.errors.length })}</h2>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left"><tr><th className="p-2">{t("import.sheet")}</th><th className="p-2">{t("import.row")}</th><th className="p-2">{t("import.field")}</th><th className="p-2">{t("import.problem")}</th></tr></thead>
                  <tbody>
                    {p.errors.map((e, i) => (
                      <tr key={i} className="border-t border-line"><td className="p-2">{e.sheet}</td><td className="p-2">{e.row}</td><td className="p-2">{e.field}</td><td className="p-2">{errLabel(e.code)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          ) : (
            <>
              <div className="max-h-96 overflow-auto rounded-xl border border-line bg-surface">
                <table className="w-full min-w-[560px] text-sm">
                  <thead className="sticky top-0 bg-sunken text-left"><tr><th className="p-2">{t("import.row")}</th><th className="p-2">{t("reports.borrower")}</th><th className="p-2">{t("loan.disbursalDate")}</th><th className="p-2 text-right">{t("import.principal")}</th><th className="p-2 text-right">{t("import.paid")}</th><th className="p-2 text-right">{t("import.outstanding")}</th></tr></thead>
                  <tbody>
                    {p.rows.map((r) => (
                      <tr key={r.row} className="border-t border-line"><td className="p-2">{r.row}</td><td className="p-2">{displayName(lang, r.name_en, r.name_ta)}<span className="block text-xs text-muted">{r.phone}</span></td><td className="p-2">{dmy(r.disbursal_date)}</td><td className="p-2 text-right tabular">{money(r.principal)}</td><td className="p-2 text-right tabular">{money(r.paid)}</td><td className="p-2 text-right tabular">{money(r.outstanding)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {commit.isSuccess ? (
                <p className="flex items-center gap-2 rounded-xl bg-paid-soft p-3 font-semibold text-paid">
                  <CheckCircle2 className="h-5 w-5" aria-hidden />{t("import.done", { count: p.loans })}
                </p>
              ) : (
                <Button size="lg" variant="paid" loading={commit.isPending} onClick={() => commit.mutate()}>
                  {t("import.commit", { count: p.loans })}
                </Button>
              )}
              {commit.error && <p role="alert" className="field-error">{commit.error instanceof ApiError ? errorMessage(commit.error) : ""}</p>}
            </>
          )}
        </>
      )}
    </div>
  );
}
