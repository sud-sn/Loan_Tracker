import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, HandCoins, MessageCircle, Phone } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import type { DueRow, Page, Reminder } from "@/api/types";
import { useLang } from "@/i18n";
import { displayName, dmy, money } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useQuickActions } from "./QuickActions";
import { Button } from "./ui/button";
import { EmptyState, ErrorState, ListSkeleton } from "./ui/states";

type Which = "today" | "overdue" | "long_unpaid" | "upcoming";

const BUCKETS = ["1_7", "8_30", "31_60", "61_90", "over_90"];

/** Due today, Overdue (grouped by age), Long unpaid and Upcoming, each row with Call / WhatsApp / Pay. */
export function DueLists({ windowDays }: { windowDays: number }) {
  const { t } = useTranslation();
  const [which, setWhich] = useState<Which>("today");
  const [sort, setSort] = useState<"overdue_days" | "overdue_amount">("overdue_days");
  const tabs: { key: Which; label: string }[] = [
    { key: "today", label: t("dues.today") },
    { key: "overdue", label: t("dues.overdue") },
    { key: "long_unpaid", label: t("dues.long_unpaid") },
    { key: "upcoming", label: t("dues.upcoming", { days: windowDays }) },
  ];
  const q = useQuery({
    queryKey: ["dues", which, sort],
    queryFn: () => api.get<Page<DueRow>>("/dues", { which, sort, page_size: 100 }),
  });
  const empty = { today: t("dues.emptyToday"), overdue: t("dues.emptyOverdue"), long_unpaid: t("dues.emptyLong"),
    upcoming: t("dues.emptyUpcoming") }[which];
  const rows = q.data?.items ?? [];
  return (
    <section aria-labelledby="dues-title" className="@container space-y-3">
      <h2 id="dues-title" className="text-xl">{t("home.lists")}</h2>
      <div role="tablist" className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1">
        {tabs.map((tab) => (
          <button key={tab.key} role="tab" aria-selected={which === tab.key} onClick={() => setWhich(tab.key)}
            className={cn("min-h-touch shrink-0 rounded-full border px-4 font-semibold",
              which === tab.key ? "border-brand bg-brand text-brand-ink" : "border-line bg-surface text-ink")}>
            {tab.label}{which === tab.key && q.data ? ` · ${q.data.total}` : ""}
          </button>
        ))}
      </div>
      {which === "overdue" && (
        <div className="flex gap-2">
          {(["overdue_days", "overdue_amount"] as const).map((s) => (
            <Button key={s} size="sm" variant={sort === s ? "secondary" : "ghost"} onClick={() => setSort(s)}>
              {s === "overdue_days" ? t("dues.sortDays") : t("dues.sortAmount")}
            </Button>
          ))}
        </div>
      )}
      {q.isLoading && <ListSkeleton rows={3} />}
      {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
      {q.isSuccess && rows.length === 0 && <EmptyState text={empty} />}
      {which === "overdue" && sort === "overdue_days"
        ? BUCKETS.map((bucket) => {
            const group = rows.filter((r) => r.bucket === bucket);
            if (!group.length) return null;
            return (
              <div key={bucket} className="space-y-2">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-late">{t(`bucket.${bucket}`)} · {group.length}</h3>
                {group.map((r) => <DueRowCard key={r.loan_id} row={r} which={which} />)}
              </div>
            );
          })
        : rows.map((r) => <DueRowCard key={r.loan_id} row={r} which={which} />)}
    </section>
  );
}

function DueRowCard({ row, which }: { row: DueRow; which: Which }) {
  const { t } = useTranslation();
  const lang = useLang();
  const qa = useQuickActions();
  const [busy, setBusy] = useState(false);
  const openWhatsApp = async () => {
    setBusy(true);
    try {
      const r = await api.get<Reminder>(`/loans/${row.loan_id}/reminder`);
      if (r.whatsapp_url) window.open(r.whatsapp_url, "_blank", "noopener");
    } finally {
      setBusy(false);
    }
  };
  const late = row.overdue_days > 0;
  const showOutstanding = which === "long_unpaid" && Number(row.overdue_amount) === 0;
  const btn = "flex min-h-touch items-center justify-center gap-1.5 rounded-xl px-2 font-semibold @4xl:min-h-[40px] @4xl:px-3 @4xl:text-sm";
  // Narrow panel: a card (name and amount, then details, then three big buttons).
  // Wide panel (container 56rem+): one row with columns, like a table. Names wrap rather than being cut.
  return (
    <article className={cn(
      "card grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 p-3 [grid-template-areas:'who_amt''info_info''act_act']",
      "@4xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1.2fr)_minmax(7.5rem,auto)_auto] @4xl:items-center @4xl:gap-x-4 @4xl:py-2",
      "@4xl:[grid-template-areas:'who_info_amt_act']",
      late && "border-l-4 border-l-late",
    )}>
      <Link to={`/loans/${row.loan_id}`} className="min-w-0 [grid-area:who]">
        <p className="text-lg font-semibold [overflow-wrap:anywhere] @4xl:text-base">{displayName(lang, row.name_en, row.name_ta)}</p>
        <p className="text-sm text-muted"><span className="whitespace-nowrap">{row.code}</span> · <span className="whitespace-nowrap">{row.loan_no}</span></p>
      </Link>
      <div className="text-right [grid-area:amt]">
        {showOutstanding && <p className="text-sm text-muted">{t("borrower.outstanding")}</p>}
        <p className="text-lg font-bold tabular @4xl:text-base">
          {money(showOutstanding ? row.outstanding : which === "long_unpaid" ? row.overdue_amount : row.amount_due)}
        </p>
        {late && (
          <p className="inline-flex items-center gap-1 text-sm font-semibold text-late">
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />{t("dues.overdueDays", { count: row.overdue_days })}
          </p>
        )}
        {!late && row.due_date && <p className="text-sm text-due">{t("dues.dueOn", { date: dmy(row.due_date) })}</p>}
      </div>
      <div className="min-w-0 text-sm text-muted [grid-area:info]">
        <p>
          {row.last_payment_on ? t("dues.lastPayment", { date: dmy(row.last_payment_on) }) : t("dues.neverPaid")}
          {which === "long_unpaid" && ` · ${t("dues.daysSince", { count: row.days_since_last_payment })}`}
          {Number(row.penalty_due) > 0 && ` · ${t("dues.penalty", { amount: money(row.penalty_due) })}`}
        </p>
        {row.multiple_overdue && (
          <p className="mt-1 inline-flex items-center gap-1 rounded-full bg-late-soft px-2 py-0.5 font-semibold text-late">
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />{t("dues.multiOverdue")}
          </p>
        )}
      </div>
      <div className="mt-2 grid grid-cols-3 gap-2 [grid-area:act] @4xl:mt-0 @4xl:flex @4xl:gap-1.5">
        <a href={row.phone ? `tel:+91${row.phone}` : undefined} aria-disabled={!row.phone}
          className={cn(btn, "border border-line bg-surface hover:bg-sunken")}>
          <Phone className="h-5 w-5 shrink-0 @4xl:h-4 @4xl:w-4" aria-hidden />{t("dues.call")}
        </a>
        <button onClick={openWhatsApp} disabled={!row.phone || busy}
          className={cn(btn, "border border-line bg-surface hover:bg-sunken disabled:opacity-50")}>
          <MessageCircle className="h-5 w-5 shrink-0 @4xl:h-4 @4xl:w-4" aria-hidden />
          <span className="min-w-0 leading-tight">{t("dues.whatsapp")}</span>
        </button>
        <button onClick={() => qa.receivePayment(row.loan_id, which === "upcoming" ? undefined : row.amount_due)}
          className={cn(btn, "bg-paid text-white hover:bg-paid/90")}>
          <HandCoins className="h-5 w-5 shrink-0 @4xl:h-4 @4xl:w-4" aria-hidden />
          <span className="leading-tight">{t("dues.recordPayment")}</span>
        </button>
      </div>
    </article>
  );
}
