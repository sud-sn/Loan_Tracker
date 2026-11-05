import { useInfiniteQuery } from "@tanstack/react-query";
import { AlertTriangle, UserPlus } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { api } from "@/api/client";
import type { BorrowerListItem, Page } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/field";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/states";
import { StatusBadge } from "@/components/ui/status";
import { DataTable } from "@/components/ui/table";
import { useLang } from "@/i18n";
import { displayName, money } from "@/lib/format";

export function BorrowersPage() {
  const { t } = useTranslation();
  const lang = useLang();
  const navigate = useNavigate();
  const [status, setStatus] = useState("");
  const [flag, setFlag] = useState("");
  const [sort, setSort] = useState("name");
  const q = useInfiniteQuery({
    queryKey: ["borrowers", status, flag, sort],
    initialPageParam: 1,
    queryFn: ({ pageParam }) => api.get<Page<BorrowerListItem>>("/borrowers", {
      page: pageParam, page_size: 30, status, sort, desc: sort === "outstanding" || sort === "overdue_days",
      has_overdue: flag === "overdue" ? true : undefined, has_active_loan: flag === "active" ? true : undefined,
    }),
    getNextPageParam: (last) => (last.page * last.page_size < last.total ? last.page + 1 : undefined),
  });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div className="space-y-4">
      <PageHeader title={t("borrower.listTitle")}
        subtitle={q.data ? t("borrower.count", { count: q.data.pages[0].total }) : undefined}
        actions={<Link to="/borrowers/new"><Button><UserPlus className="h-5 w-5" aria-hidden />{t("borrower.add")}</Button></Link>} />
      {/* Filters: stacked on a phone, one toolbar row on a laptop. */}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3 lg:max-w-4xl">
        <Field label={t("borrower.filterStatus")}>
          {(id) => (
            <Select id={id} value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">{t("app.all")}</option>
              {["active", "blocked", "closed"].map((s) => <option key={s} value={s}>{t(`status.${s}`)}</option>)}
            </Select>
          )}
        </Field>
        <Field label={t("app.show")}>
          {(id) => (
            <Select id={id} value={flag} onChange={(e) => setFlag(e.target.value)}>
              <option value="">{t("app.all")}</option>
              <option value="overdue">{t("borrower.filterOverdue")}</option>
              <option value="active">{t("borrower.filterActive")}</option>
            </Select>
          )}
        </Field>
        <Field label={t("borrower.sort")}>
          {(id) => (
            <Select id={id} value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="name">{t("borrower.sortName")}</option>
              <option value="code">{t("borrower.sortCode")}</option>
              <option value="outstanding">{t("borrower.sortOutstanding")}</option>
              <option value="overdue_days">{t("borrower.sortOverdue")}</option>
            </Select>
          )}
        </Field>
      </div>
      {q.isLoading && <ListSkeleton />}
      {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
      {q.isSuccess && items.length === 0 && (
        <EmptyState text={status || flag ? t("borrower.emptyFilter") : t("borrower.empty")} />
      )}
      <ul className="space-y-2 lg:hidden">
        {items.map((b) => (
          <li key={b.id}>
            <Link to={`/borrowers/${b.id}`} className="card flex items-start justify-between gap-3 p-3 hover:bg-sunken">
              <div className="min-w-0">
                <p className="truncate text-lg font-semibold">{displayName(lang, b.name_en, b.name_ta)}</p>
                <p className="text-sm text-muted">{b.code}{b.phone ? ` · ${b.phone}` : ""}</p>
                <div className="mt-1 flex flex-wrap gap-1">
                  {b.status !== "active" && <StatusBadge status={b.status} />}
                  {b.profile_incomplete && <StatusBadge status="incomplete" />}
                  {b.multiple_overdue && (
                    <span className="inline-flex items-center gap-1 text-sm font-semibold text-late">
                      <AlertTriangle className="h-4 w-4" aria-hidden />{t("dues.multiOverdue")}
                    </span>
                  )}
                </div>
              </div>
              <div className="shrink-0 text-right">
                <p className="font-bold tabular">{money(b.outstanding)}</p>
                {Number(b.overdue_amount) > 0 && (
                  <p className="text-sm font-semibold text-late">{t("dues.overdueDays", { count: b.overdue_days })}</p>
                )}
              </div>
            </Link>
          </li>
        ))}
      </ul>
      {items.length > 0 && (
        <div className="hidden lg:block">
          <DataTable rows={items} rowKey={(b) => b.id} onRowClick={(b) => navigate(`/borrowers/${b.id}`)}
            caption={t("borrower.listTitle")}
            rowClassName={(b) => (Number(b.overdue_amount) > 0 ? "shadow-[inset_4px_0_0_rgb(var(--late))]" : undefined)}
            columns={[
              { key: "name", header: t("borrower.sortName"), cell: (b) => (
                <Link to={`/borrowers/${b.id}`} onClick={(e) => e.stopPropagation()} className="font-semibold hover:underline">
                  {displayName(lang, b.name_en, b.name_ta)}
                </Link>
              ) },
              { key: "code", header: t("borrower.code"), cell: (b) => <span className="whitespace-nowrap tabular">{b.code}</span> },
              { key: "phone", header: t("borrower.phone"), cell: (b) => <span className="tabular">{b.phone ?? "—"}</span> },
              { key: "status", header: t("borrower.statusLabel"), cell: (b) => (
                <div className="flex flex-wrap gap-1">
                  <StatusBadge status={b.profile_incomplete ? "incomplete" : b.status} />
                  {b.multiple_overdue && (
                    <span className="inline-flex items-center gap-1 text-sm font-semibold text-late" title={t("dues.multiOverdue")}>
                      <AlertTriangle className="h-4 w-4" aria-hidden /><span className="sr-only">{t("dues.multiOverdue")}</span>2+
                    </span>
                  )}
                </div>
              ) },
              { key: "loans", header: t("borrower.activeLoans"), align: "right", cell: (b) => b.active_loans },
              { key: "outstanding", header: t("borrower.outstanding"), align: "right", cell: (b) => (
                <span className="font-semibold">{money(b.outstanding)}</span>) },
              { key: "overdue", header: t("borrower.overdue"), align: "right", cell: (b) => (
                Number(b.overdue_amount) > 0 ? <span className="font-semibold text-late">{money(b.overdue_amount)}</span> : "—") },
              { key: "days", header: t("borrower.sortOverdue"), align: "right", cell: (b) => (
                b.overdue_days > 0 ? <span className="whitespace-nowrap font-semibold text-late">{t("dues.overdueDays", { count: b.overdue_days })}</span> : "—") },
            ]} />
        </div>
      )}
      {q.hasNextPage && (
        <Button variant="outline" className="w-full lg:mx-auto lg:flex lg:w-auto" loading={q.isFetchingNextPage} onClick={() => void q.fetchNextPage()}>
          {t("app.loadMore")}
        </Button>
      )}
    </div>
  );
}
