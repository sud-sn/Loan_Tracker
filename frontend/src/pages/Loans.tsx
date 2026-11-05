import { useInfiniteQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { api } from "@/api/client";
import type { LoanListItem, Page } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/states";
import { StatusBadge } from "@/components/ui/status";
import { DataTable } from "@/components/ui/table";
import { useLang } from "@/i18n";
import { displayName, dmy, money } from "@/lib/format";
import { cn } from "@/lib/utils";

export function LoansPage() {
  const { t } = useTranslation();
  const lang = useLang();
  const navigate = useNavigate();
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
      <PageHeader title={t("loan.listTitle")} subtitle={q.data ? t("loan.count", { count: q.data.pages[0].total }) : undefined}
        actions={<Link to="/loans/new"><Button><Plus className="h-5 w-5" aria-hidden />{t("loan.new")}</Button></Link>} />
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
      <ul className="space-y-2 lg:hidden">
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
      {items.length > 0 && (
        <div className="hidden lg:block">
          <DataTable rows={items} rowKey={(l) => l.id} onRowClick={(l) => navigate(`/loans/${l.id}`)} caption={t("loan.listTitle")}
            rowClassName={(l) => (l.overdue_days > 0 ? "shadow-[inset_4px_0_0_rgb(var(--late))]" : undefined)}
            columns={[
              { key: "no", header: t("loan.loanNo"), cell: (l) => (
                <Link to={`/loans/${l.id}`} onClick={(e) => e.stopPropagation()} className="whitespace-nowrap font-semibold tabular hover:underline">{l.loan_no}</Link>) },
              { key: "who", header: t("reports.borrower"), cell: (l) => (
                <div className="min-w-0"><p className="font-semibold">{displayName(lang, l.borrower.name_en, l.borrower.name_ta)}</p>
                  <p className="whitespace-nowrap text-xs text-muted tabular">{l.borrower.code}</p></div>) },
              { key: "amount", header: t("loan.principal"), align: "right", cell: (l) => money(l.principal) },
              { key: "given", header: t("loan.disbursalDate"), cell: (l) => <span className="whitespace-nowrap tabular">{dmy(l.disbursal_date)}</span> },
              { key: "method", header: t("loan.method"), wideOnly: true, cell: (l) => <span className="text-muted">{t(`method.${l.method}`)}</span> },
              { key: "maturity", header: t("loan.maturity"), wideOnly: true, cell: (l) => <span className="whitespace-nowrap tabular">{dmy(l.maturity_date)}</span> },
              { key: "status", header: t("loan.status"), cell: (l) => <StatusBadge status={l.status} /> },
              { key: "outstanding", header: t("loan.outstanding"), align: "right", cell: (l) => <span className="font-semibold">{money(l.outstanding)}</span> },
              { key: "late", header: t("borrower.sortOverdue"), align: "right", cell: (l) => (
                l.overdue_days > 0 ? <span className="whitespace-nowrap font-semibold text-late">{t("dues.overdueDays", { count: l.overdue_days })}</span> : "—") },
            ]} />
        </div>
      )}
      {q.hasNextPage && (
        <Button variant="outline" className="w-full lg:mx-auto lg:flex lg:w-auto" loading={q.isFetchingNextPage}
          onClick={() => void q.fetchNextPage()}>{t("app.loadMore")}</Button>
      )}
    </div>
  );
}
