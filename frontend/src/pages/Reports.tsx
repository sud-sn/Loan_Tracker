import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api, openFile } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/states";
import { useLang } from "@/i18n";
import { displayName, dmy, money, todayIST } from "@/lib/format";
import { cn } from "@/lib/utils";

type Kind = "collections" | "outstanding" | "ageing" | "interest";
type Row = Record<string, string | number | null>;

export function ReportsPage() {
  const { t } = useTranslation();
  const lang = useLang();
  const [kind, setKind] = useState<Kind>("collections");
  const [start, setStart] = useState(todayIST().slice(0, 8) + "01");
  const [end, setEnd] = useState(todayIST());
  const [group, setGroup] = useState<"day" | "month">("day");
  const [exportLang, setExportLang] = useState(lang);
  const dated = kind === "collections" || kind === "interest";
  const q = useQuery({
    queryKey: ["report", kind, start, end, group],
    queryFn: () => api.get<Row[]>(`/reports/${kind}`, dated ? { start, end, group } : undefined),
  });
  const tabs: [Kind, string][] = [["collections", t("reports.collections")], ["outstanding", t("reports.outstanding")],
    ["ageing", t("reports.ageing")], ["interest", t("reports.interest")]];
  const rows = q.data ?? [];
  return (
    <div className="space-y-4">
      <h1 className="text-2xl">{t("reports.title")}</h1>
      <div role="tablist" className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1">
        {tabs.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={kind === k} onClick={() => setKind(k)}
            className={cn("min-h-touch shrink-0 rounded-full border px-4 font-semibold", kind === k ? "border-brand bg-brand text-brand-ink" : "border-line bg-surface")}>
            {label}
          </button>
        ))}
      </div>
      {dated && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Field label={t("reports.from")}>{(id) => <Input id={id} type="date" value={start} onChange={(e) => setStart(e.target.value)} />}</Field>
          <Field label={t("reports.to")}>{(id) => <Input id={id} type="date" value={end} max={todayIST()} onChange={(e) => setEnd(e.target.value)} />}</Field>
          <div className="col-span-2 flex items-end gap-2">
            {(["day", "month"] as const).map((g) => (
              <Button key={g} variant={group === g ? "secondary" : "outline"} onClick={() => setGroup(g)}>
                {g === "day" ? t("reports.groupDay") : t("reports.groupMonth")}
              </Button>
            ))}
          </div>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted">{t("reports.exportIn")}</span>
        {(["ta", "en"] as const).map((l) => (
          <Button key={l} size="sm" variant={exportLang === l ? "secondary" : "ghost"} onClick={() => setExportLang(l)}>
            {l === "ta" ? "தமிழ்" : "English"}
          </Button>
        ))}
        {(["pdf", "csv"] as const).map((fmt) => (
          <Button key={fmt} size="sm" variant="outline"
            onClick={() => void openFile(`/reports/${kind}/export`, { fmt, lang: exportLang, start, end, group }, fmt === "csv")}>
            <Download className="h-4 w-4" aria-hidden />{fmt.toUpperCase()}
          </Button>
        ))}
      </div>
      {q.isLoading && <ListSkeleton rows={2} />}
      {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
      {q.isSuccess && rows.length === 0 && <EmptyState text={t("reports.empty")} />}
      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-line bg-surface">
          <table className="w-full text-xs sm:text-sm">
            <thead className="bg-sunken text-left">
              {kind === "collections" && <tr><th className="px-1.5 py-2 sm:p-2">{t("reports.period")}</th><th className="hidden p-2 text-right sm:table-cell">{t("reports.count")}</th><th className="px-1.5 py-2 text-right sm:p-2">{t("payment.principal")}</th><th className="px-1.5 py-2 text-right sm:p-2">{t("payment.interest")}</th><th className="px-1.5 py-2 text-right sm:p-2">{t("reports.total")}</th></tr>}
              {kind === "interest" && <tr><th className="px-1.5 py-2 sm:p-2">{t("reports.period")}</th><th className="px-1.5 py-2 text-right sm:p-2">{t("payment.interest")}</th><th className="px-1.5 py-2 text-right sm:p-2">{t("payment.penalty")}</th></tr>}
              {kind === "outstanding" && <tr><th className="px-1.5 py-2 sm:p-2">{t("reports.borrower")}</th><th className="px-1.5 py-2 text-right sm:p-2">{t("reports.loans")}</th><th className="px-1.5 py-2 text-right sm:p-2">{t("borrower.outstanding")}</th><th className="px-1.5 py-2 text-right sm:p-2">{t("borrower.overdue")}</th></tr>}
              {kind === "ageing" && <tr><th className="px-1.5 py-2 sm:p-2">{t("reports.bucket")}</th><th className="px-1.5 py-2 text-right sm:p-2">{t("reports.loans")}</th><th className="px-1.5 py-2 text-right sm:p-2">{t("reports.amount")}</th></tr>}
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-t border-line">
                  {kind === "collections" && <><td className="px-1.5 py-2 sm:p-2">{dmy(String(r.period))}</td><td className="hidden p-2 text-right sm:table-cell">{r.count}</td><td className="px-1.5 py-2 text-right sm:p-2 tabular">{money(r.principal)}</td><td className="px-1.5 py-2 text-right sm:p-2 tabular">{money(r.interest)}</td><td className="px-1.5 py-2 text-right sm:p-2 font-semibold tabular">{money(r.total)}</td></>}
                  {kind === "interest" && <><td className="px-1.5 py-2 sm:p-2">{dmy(String(r.period))}</td><td className="px-1.5 py-2 text-right sm:p-2 tabular">{money(r.interest)}</td><td className="px-1.5 py-2 text-right sm:p-2 tabular">{money(r.penalty)}</td></>}
                  {kind === "outstanding" && <><td className="px-1.5 py-2 sm:p-2">{displayName(lang, r.name_en as string, r.name_ta as string)}<span className="block text-xs text-muted">{r.code}</span></td><td className="px-1.5 py-2 text-right sm:p-2">{r.active_loans}</td><td className="px-1.5 py-2 text-right sm:p-2 tabular">{money(r.outstanding)}</td><td className="px-1.5 py-2 text-right sm:p-2 tabular text-late">{money(r.overdue_amount)}</td></>}
                  {kind === "ageing" && <><td className="px-1.5 py-2 sm:p-2">{t(`bucket.${r.bucket}`)}</td><td className="px-1.5 py-2 text-right sm:p-2">{r.count}</td><td className="px-1.5 py-2 text-right sm:p-2 tabular">{money(r.amount)}</td></>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
