import { useInfiniteQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import type { LoanListItem, Page } from "@/api/types";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/states";
import { StatusBadge } from "@/components/ui/status";
import { useLang } from "@/i18n";
import { displayName, dmy, money } from "@/lib/format";
import { cn } from "@/lib/utils";

export function LoansPage() {
  const { t } = useTranslation();
  const lang = useLang();
  const [status, setStatus] = useState<"active" | "closed" | "written_off">("active");
  const q = useInfiniteQuery({
    queryKey: ["loans", status],
    initialPageParam: 1,
    queryFn: ({ pageParam }) => api.get<Page<LoanListItem>>("/loans", { status, page: pageParam, page_size: 30 }),
    getNextPageParam: (last) => (last.page * last.page_size < last.total ? last.page + 1 : undefined),
  });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl">{t("loan.listTitle")}</h1>
        <Link to="/loans/new"><Button><Plus className="h-5 w-5" aria-hidden />{t("loan.new")}</Button></Link>
      </div>
      <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1" role="tablist">
        {([["active", t("loan.filterActive")], ["closed", t("loan.filterClosed")], ["written_off", t("loan.filterWritten")]] as const).map(([v, label]) => (
          <button key={v} role="tab" aria-selected={status === v} onClick={() => setStatus(v)}
            className={cn("min-h-touch shrink-0 rounded-full border px-4 font-semibold", status === v ? "border-brand bg-brand text-brand-ink" : "border-line bg-surface")}>
            {label}
          </button>
        ))}
      </div>
      {q.isLoading && <ListSkeleton />}
      {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
      {q.isSuccess && items.length === 0 && <EmptyState text={t("loan.empty")} />}
      <ul className="space-y-2">
        {items.map((l) => (
          <li key={l.id}>
            <Link to={`/loans/${l.id}`} className="card flex items-start justify-between gap-3 p-3 hover:bg-sunken">
              <div className="min-w-0">
                <p className="truncate text-lg font-semibold">{displayName(lang, l.borrower.name_en, l.borrower.name_ta)}</p>
                <p className="text-sm text-muted"><span className="whitespace-nowrap">{l.loan_no}</span> · <span className="whitespace-nowrap">{l.borrower.code}</span></p>
                <p className="text-sm text-muted">{money(l.principal)} · {dmy(l.disbursal_date)}</p>
              </div>
              <div className="shrink-0 text-right">
                <StatusBadge status={l.status} />
                <p className="mt-1 font-bold tabular">{money(l.outstanding)}</p>
                {l.overdue_days > 0 && <p className="text-sm text-late">{t("dues.overdueDays", { count: l.overdue_days })}</p>}
              </div>
            </Link>
          </li>
        ))}
      </ul>
      {q.hasNextPage && <Button variant="outline" className="w-full" onClick={() => void q.fetchNextPage()}>{t("app.loadMore")}</Button>}
    </div>
  );
}
