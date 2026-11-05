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

  const exportButtons = isOwner && (
    <>
      <Button variant="outline" size="sm" onClick={() => void openFile("/daybook/export", { start: day, end: day, fmt: "pdf", lang })}>
        <Download className="h-4 w-4" aria-hidden />{t("home.export")} · PDF
      </Button>
      <Button variant="outline" size="sm" onClick={() => void openFile("/daybook/export", { start: day, end: day, fmt: "csv", lang }, true)}>
        <Download className="h-4 w-4" aria-hidden />CSV
      </Button>
    </>
  );
  const hasModes = !!b && Object.keys(b.by_mode).length > 0;

  return (
    <div className="space-y-6">
      {/* Date bar: centred on a phone, left-aligned with the day's actions on the right on a laptop. */}
      <div className="flex items-center gap-2">
        <Button size="icon" variant="outline" aria-label={t("app.previousDay")} onClick={() => setDay(addDays(day, -1))}>
          <ChevronLeft className="h-5 w-5" aria-hidden />
        </Button>
        <div className="min-w-0 flex-1 text-center lg:flex-none lg:px-2 lg:text-left">
          <h1 className="text-xl xl:text-2xl">{day === today ? t("home.title") : dmy(day)}</h1>
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
        {day !== today && (
          <Button variant="secondary" className="hidden lg:inline-flex" onClick={() => setDay(today)}>{t("app.today")}</Button>
        )}
        <div className="hidden flex-1 justify-end gap-2 lg:flex">{exportButtons}</div>
      </div>
      {day !== today && (
        <Button variant="secondary" className="w-full lg:hidden" onClick={() => setDay(today)}>{t("app.today")}</Button>
      )}

      {book.isError && <ErrorState error={book.error} onRetry={() => void book.refetch()} />}
      <section aria-label={t("home.title")} className="card @container overflow-hidden p-0">
        {/* Columns follow the card's own width: 2 on a phone, 3 on a tablet or small laptop, 6 when there is room. */}
        <div className="grid grid-cols-2 gap-px bg-line @md:grid-cols-3 @5xl:grid-cols-6">
          <Stat label={t("home.opening")} value={b ? (b.tracked ? money(b.opening_balance) : "—") : null} />
          <Stat label={t("home.moneyIn")} value={b ? money(b.money_in) : null} tone="in" />
          <Stat label={t("home.moneyOut")} value={b ? money(b.money_out) : null} tone="out" />
          <Stat label={t("home.closing")} value={b ? (b.tracked ? money(b.closing_balance) : "—") : null} strong />
          <Stat label={t("home.week")} value={b ? money(b.week.net) : null}
            sub={b ? [`+${money(b.week.in)}`, `−${money(b.week.out)}`] : undefined} tone={b && Number(b.week.net) < 0 ? "out" : "in"} />
          <Stat label={t("home.month")} value={b ? money(b.month.net) : null}
            sub={b ? [`+${money(b.month.in)}`, `−${money(b.month.out)}`] : undefined} tone={b && Number(b.month.net) < 0 ? "out" : "in"} />
        </div>
        {/* Footer of the same card, always present, so nothing below moves when the data arrives. */}
        <div className="flex min-h-touch flex-wrap items-center justify-between gap-x-4 gap-y-1 border-t border-line px-3 py-1">
          <p className="text-sm text-muted">
            {b && !b.tracked ? (b.balance_start_date ? t("home.notTracked", { date: dmy(b.balance_start_date) }) : t("home.setStart"))
              : b ? `${t("home.net")}: ${money(b.net)}` : "\u00a0"}
          </p>
          <button className="min-h-touch text-sm font-semibold text-brand underline disabled:no-underline disabled:opacity-50"
            onClick={() => setShowModes((v) => !v)} disabled={!hasModes} aria-expanded={showModes}>{t("home.byMode")}</button>
        </div>
        {showModes && b && (
          <div className="grid grid-cols-2 gap-2 border-t border-line p-3 sm:grid-cols-4">
            {Object.entries(b.by_mode).map(([mode, v]) => (
              <div key={mode} className="rounded-xl border border-line bg-surface p-3 text-sm">
                <p className="font-semibold">{t(`mode.${mode}`)}</p>
                <p className="text-moneyin tabular">+ {money(v.in)}</p>
                <p className="text-moneyout tabular">− {money(v.out)}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      <QuickAddButtons />

      {/* On very wide screens (main area 110 rem+, e.g. 2560 px monitors) today's log and "who has to pay"
          sit side by side instead of leaving the screen half empty. */}
      <div className="grid gap-6 @[110rem]/main:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] @[110rem]/main:items-start">
      {/* Today's log: money in and money out side by side (equal height) from tablet width up. */}
      <section aria-label={t("home.title")} className="space-y-3">
        <div className="grid gap-4 md:grid-cols-2">
          <EntryList title={t("home.moneyIn")} icon="in" entries={b?.entries_in} empty={t("home.nothingIn")}
            loading={book.isLoading} onEdit={setEditing} />
          <EntryList title={t("home.moneyOut")} icon="out" entries={b?.entries_out} empty={t("home.nothingOut")}
            loading={book.isLoading} onEdit={setEditing} />
        </div>
        {exportButtons && <div className="flex flex-wrap gap-2 lg:hidden">{exportButtons}</div>}
      </section>

      <div className="space-y-6">
      {/* Who has to pay: full width, so each row lays out as one line on a laptop. */}
      <DueLists windowDays={settings.data?.due_window_days ?? 7} />

      <section aria-labelledby="cards" className="space-y-3">
        <h2 id="cards" className="text-xl">{t("home.cards")}</h2>
        {dash.data ? (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
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
        ) : <div className="grid grid-cols-2 gap-3 md:grid-cols-3"><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /></div>}
      </section>
      </div>
      </div>
      {editing && editing.source_type === "cash_entry" && (
        <Suspense fallback={null}><CashEntrySheet direction={editing.direction} onClose={() => setEditing(null)}
          existing={{ id: editing.source_id, version: editing.version ?? 1, amount: editing.amount, note: editing.note,
            mode: editing.mode, entry_date: editing.date }} /></Suspense>
      )}
    </div>
  );
}

function Stat({ label, value, tone, strong, sub }: { label: string; value: string | null; tone?: "in" | "out"; strong?: boolean;
  sub?: string[] }) {
  return (
    <div className="min-w-0 bg-surface p-3 xl:p-4">
      <p className="text-sm text-muted">{label}</p>
      {value === null ? <Skeleton className="mt-1 h-6 w-24" /> : (
        <p className={cn("truncate text-lg font-bold tabular xl:text-xl", tone === "in" && "text-moneyin",
          tone === "out" && "text-moneyout", strong && "text-brand")} title={value}>{value}</p>
      )}
      {/* In and out wrap onto two lines when the column is narrow; never cut off. */}
      {sub && <p className="flex flex-wrap gap-x-1.5 text-xs text-muted tabular">{sub.map((s) => <span key={s}>{s}</span>)}</p>}
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
    <section className="card @container flex min-h-[22rem] flex-col p-0 md:min-h-0">
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
            // Narrow card: name and amount, details below. Wide card (36rem+): name | references | amount.
            <div className="grid min-h-touch grid-cols-[minmax(0,1fr)_auto] items-start gap-x-3 px-4 py-2.5 @xl:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)_auto]">
              <div className="min-w-0">
                <p className="truncate font-semibold">{label}</p>
                <p className="truncate text-sm text-muted">{kind}</p>
              </div>
              <div className="col-span-2 row-start-2 min-w-0 text-sm text-muted @xl:col-span-1 @xl:row-start-auto">
                <p className="truncate">
                  {e.code ? <span className="whitespace-nowrap">{e.code}</span> : null}
                  {e.loan_no ? <> · <span className="whitespace-nowrap">{e.loan_no}</span></> : null}
                  {e.code || e.loan_no ? " · " : ""}{t(`mode.${e.mode}`)}
                </p>
                {e.principal && e.kind !== "loan" && (
                  <p className="truncate">{t("payment.principal")} {money(e.principal)} · {t("payment.interest")} {money(e.interest)}</p>
                )}
                {e.note && <p className="truncate">{e.note}</p>}
              </div>
              <div className="col-start-2 row-start-1 flex shrink-0 items-center gap-1 @xl:col-start-3">
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
