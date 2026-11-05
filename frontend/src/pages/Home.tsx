import { useQuery } from "@tanstack/react-query";
import { ArrowDownLeft, ArrowUpRight, CalendarDays, ChevronLeft, ChevronRight, Download, Pencil, Undo2 } from "lucide-react";
import { lazy, Suspense, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";

import { api, openFile } from "@/api/client";
import type { AppSettings, Dashboard, Daybook, DaybookEntry } from "@/api/types";
import { DueLists } from "@/components/DueList";
import { QuickAddButtons } from "@/components/QuickActions";
import { Button } from "@/components/ui/button";
import { ErrorState, Skeleton } from "@/components/ui/states";
import { useAuth } from "@/hooks/useAuth";
import { useLang } from "@/i18n";
import { addDays, displayName, dmy, longDate, money, todayIST } from "@/lib/format";
import { cn } from "@/lib/utils";

const CashEntrySheet = lazy(() => import("@/components/CashEntrySheet").then((m) => ({ default: m.CashEntrySheet })));

export function HomePage() {
  const { t } = useTranslation();
  const lang = useLang();
  const { isOwner } = useAuth();
  const [params, setParams] = useSearchParams();
  const today = todayIST();
  const day = params.get("d") ?? today;
  const setDay = (d: string) => setParams(d === today ? {} : { d }, { replace: true });
  const [showModes, setShowModes] = useState(false);
  const [editing, setEditing] = useState<DaybookEntry | null>(null);
  const book = useQuery({ queryKey: ["daybook", day], queryFn: () => api.get<Daybook>("/daybook", { on: day }) });
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<Dashboard>("/dashboard") });
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.get<AppSettings>("/settings") });
  const b = book.data;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-2">
        <Button size="icon" variant="outline" aria-label={t("app.previousDay")} onClick={() => setDay(addDays(day, -1))}>
          <ChevronLeft className="h-5 w-5" aria-hidden />
        </Button>
        <div className="min-w-0 flex-1 text-center">
          <h1 className="text-xl">{day === today ? t("home.title") : dmy(day)}</h1>
          <p className="text-sm text-muted">{longDate(day, lang)}</p>
        </div>
        <label className="relative inline-flex min-h-touch min-w-touch cursor-pointer items-center justify-center rounded-xl border border-line bg-surface">
          <CalendarDays className="h-5 w-5" aria-hidden />
          <span className="sr-only">{t("app.pickDate")}</span>
          <input type="date" max={today} value={day} onChange={(e) => e.target.value && setDay(e.target.value)}
            className="absolute inset-0 cursor-pointer opacity-0" />
        </label>
        <Button size="icon" variant="outline" aria-label={t("app.nextDay")} disabled={day >= today}
          onClick={() => setDay(addDays(day, 1))}>
          <ChevronRight className="h-5 w-5" aria-hidden />
        </Button>
      </div>
      {day !== today && (
        <Button variant="secondary" className="w-full" onClick={() => setDay(today)}>{t("app.today")}</Button>
      )}

      {book.isError && <ErrorState error={book.error} onRetry={() => void book.refetch()} />}
      <section aria-label={t("home.title")} className="card grid grid-cols-2 gap-px overflow-hidden bg-line p-0 sm:grid-cols-4">
        <Stat label={t("home.opening")} value={b ? (b.tracked ? money(b.opening_balance) : "—") : null} />
        <Stat label={t("home.moneyIn")} value={b ? money(b.money_in) : null} tone="in" />
        <Stat label={t("home.moneyOut")} value={b ? money(b.money_out) : null} tone="out" />
        <Stat label={t("home.closing")} value={b ? (b.tracked ? money(b.closing_balance) : "—") : null} strong />
      </section>
      {b && !b.tracked && (
        <p className="text-sm text-muted">
          {b.balance_start_date ? t("home.notTracked", { date: dmy(b.balance_start_date) }) : t("home.setStart")}
        </p>
      )}
      {/* Always rendered so nothing below moves when the day's data arrives. */}
      <div className="min-h-touch">
          <button className="min-h-touch text-sm font-semibold text-brand underline disabled:no-underline disabled:opacity-50"
            onClick={() => setShowModes((s) => !s)} disabled={!b || Object.keys(b.by_mode).length === 0}
            aria-expanded={showModes}>{t("home.byMode")}</button>
          {showModes && b && (
            <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {Object.entries(b.by_mode).map(([mode, v]) => (
                <div key={mode} className="rounded-xl border border-line bg-surface p-3 text-sm">
                  <p className="font-semibold">{t(`mode.${mode}`)}</p>
                  <p className="text-moneyin tabular">+ {money(v.in)}</p>
                  <p className="text-moneyout tabular">− {money(v.out)}</p>
                </div>
              ))}
            </div>
          )}
      </div>

      <QuickAddButtons />

      <div className="grid gap-4 lg:grid-cols-2">
        <EntryList title={t("home.moneyIn")} icon="in" entries={b?.entries_in} empty={t("home.nothingIn")}
          loading={book.isLoading} onEdit={setEditing} />
        <EntryList title={t("home.moneyOut")} icon="out" entries={b?.entries_out} empty={t("home.nothingOut")}
          loading={book.isLoading} onEdit={setEditing} />
      </div>
      {b && (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <Total label={t("home.net")} value={b.net} />
          <Total label={t("home.week")} value={b.week.net} sub={`+${money(b.week.in)} / −${money(b.week.out)}`} />
          <Total label={t("home.month")} value={b.month.net} sub={`+${money(b.month.in)} / −${money(b.month.out)}`} />
        </div>
      )}
      {isOwner && (
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => void openFile("/daybook/export", { start: day, end: day, fmt: "pdf", lang })}>
            <Download className="h-4 w-4" aria-hidden />{t("home.export")} · PDF
          </Button>
          <Button variant="outline" size="sm" onClick={() => void openFile("/daybook/export", { start: day, end: day, fmt: "csv", lang }, true)}>
            <Download className="h-4 w-4" aria-hidden />CSV
          </Button>
        </div>
      )}

      <DueLists windowDays={settings.data?.due_window_days ?? 7} />

      <section aria-labelledby="cards" className="space-y-3">
        <h2 id="cards" className="text-xl">{t("home.cards")}</h2>
        {dash.data ? (
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
            <DashCard label={t("dash.principalOutstanding")} value={money(dash.data.principal_outstanding)} />
            <DashCard label={t("dash.toReceive")} value={money(dash.data.total_to_receive)} />
            <DashCard label={t("dash.collectedMonth")} value={money(dash.data.collected_this_month.total)}
              sub={`${t("dash.principalPart", { amount: money(dash.data.collected_this_month.principal) })} · ${t("dash.interestPart", { amount: money(dash.data.collected_this_month.interest) })}`} />
            <DashCard label={t("dash.interestMonth")} value={money(dash.data.interest_this_month)}
              sub={`${t("dash.interestToDate")}: ${money(dash.data.interest_to_date)}`} />
            <DashCard label={t("dash.dueToday")} value={money(dash.data.due_today.amount)}
              sub={t("dash.loans", { count: dash.data.due_today.count })} tone="due" />
            <DashCard label={t("dash.overdue")} value={money(dash.data.overdue.amount)}
              sub={t("dash.loans", { count: dash.data.overdue.count })} tone="late" />
            <DashCard label={t("dash.longUnpaid")} value={String(dash.data.long_unpaid.count)} tone="late" />
            <DashCard label={t("dash.activeLoans")} value={String(dash.data.active_loans)} />
            <DashCard label={t("dash.activeBorrowers")} value={String(dash.data.active_borrowers)} />
          </div>
        ) : <div className="grid grid-cols-2 gap-3"><Skeleton className="h-20" /><Skeleton className="h-20" /></div>}
      </section>
      {editing && editing.source_type === "cash_entry" && (
        <Suspense fallback={null}><CashEntrySheet direction={editing.direction} onClose={() => setEditing(null)}
          existing={{ id: editing.source_id, version: editing.version ?? 1, amount: editing.amount, note: editing.note,
            mode: editing.mode, entry_date: editing.date }} /></Suspense>
      )}
    </div>
  );
}

function Stat({ label, value, tone, strong }: { label: string; value: string | null; tone?: "in" | "out"; strong?: boolean }) {
  return (
    <div className="bg-surface p-3">
      <p className="text-sm text-muted">{label}</p>
      {value === null ? <Skeleton className="mt-1 h-6 w-24" /> : (
        <p className={cn("text-lg font-bold tabular", tone === "in" && "text-moneyin", tone === "out" && "text-moneyout",
          strong && "text-brand")}>{value}</p>
      )}
    </div>
  );
}

function Total({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-3">
      <p className="text-sm text-muted">{label}</p>
      <p className={cn("font-bold tabular", Number(value) < 0 ? "text-moneyout" : "text-moneyin")}>{money(value)}</p>
      {sub && <p className="text-xs text-muted tabular">{sub}</p>}
    </div>
  );
}

function DashCard({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "due" | "late" }) {
  return (
    <div className={cn("card p-3", tone === "due" && "border-l-4 border-l-due", tone === "late" && "border-l-4 border-l-late")}>
      <p className="text-sm text-muted">{label}</p>
      <p className="text-lg font-bold tabular">{value}</p>
      {sub && <p className="text-sm text-muted">{sub}</p>}
    </div>
  );
}

function EntryList({ title, icon, entries, empty, loading, onEdit }: { title: string; icon: "in" | "out";
  entries?: DaybookEntry[]; empty: string; loading: boolean; onEdit: (e: DaybookEntry) => void }) {
  const { t } = useTranslation();
  const lang = useLang();
  const Icon = icon === "in" ? ArrowDownLeft : ArrowUpRight;
  return (
    // A fixed minimum height keeps whatever comes next below the first screen while the day loads,
    // so nothing visible jumps when the entries arrive (layout shift).
    <section className="card min-h-[22rem] p-0">
      <h2 className={cn("flex items-center gap-2 border-b border-line px-4 py-3 text-lg", icon === "in" ? "text-moneyin" : "text-moneyout")}>
        <Icon className="h-5 w-5" aria-hidden />{title}
      </h2>
      {loading && <div className="space-y-2 p-4"><Skeleton /><Skeleton className="w-1/2" /></div>}
      {!loading && !entries?.length && <p className="p-4 text-muted">{empty}</p>}
      <ul className="divide-y divide-line">
        {entries?.map((e) => {
          const label = e.code ? displayName(lang, e.name_en, e.name_ta) : (lang === "ta" ? e.category_ta : e.category_en);
          const kind = { payment: t("home.repayments"), settlement: t("payment.settlement"), reversal: t("home.reversed"),
            loan: t("home.loansGiven"), income: t("home.otherIncome"), expense: t("home.ownSpending") }[e.kind];
          const to = e.loan_id ? `/loans/${e.loan_id}` : undefined;
          const body = (
            <div className="flex min-h-touch items-start justify-between gap-3 px-4 py-2.5">
              <div className="min-w-0">
                <p className="truncate font-semibold">{label}</p>
                <p className="text-sm text-muted">
                  {kind}{e.code ? ` · ${e.code}` : ""}{e.loan_no ? ` · ${e.loan_no}` : ""} · {t(`mode.${e.mode}`)}
                </p>
                {e.principal && e.kind !== "loan" && (
                  <p className="text-sm text-muted">
                    {t("payment.principal")} {money(e.principal)} · {t("payment.interest")} {money(e.interest)}
                  </p>
                )}
                {e.note && <p className="truncate text-sm text-muted">{e.note}</p>}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {e.kind === "reversal" && <Undo2 className="h-4 w-4 text-late" aria-label={t("home.reversed")} />}
                <span className={cn("font-bold tabular", icon === "in" ? "text-moneyin" : "text-moneyout")}>{money(e.amount)}</span>
                {e.source_type === "cash_entry" && <Pencil className="h-4 w-4 text-muted" aria-hidden />}
              </div>
            </div>
          );
          return (
            <li key={`${e.source_type}-${e.source_id}`}>
              {to ? <Link to={to} className="block hover:bg-sunken">{body}</Link>
                : <button className="block w-full text-left hover:bg-sunken" onClick={() => onEdit(e)}>{body}</button>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
