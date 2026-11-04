import { useTranslation } from "react-i18next";

import { dmy, money } from "@/lib/format";
import { cn } from "@/lib/utils";

import { StatusBadge } from "./ui/status";

export interface ScheduleRowView {
  seq: number;
  due_date: string;
  installment: string;
  principal_part: string;
  interest_part: string;
  closing_balance: string;
  status?: string;
  unpaid?: string;
}

/**
 * The repayment schedule. A table on wider screens; on a phone each installment is a small card so
 * principal, interest and balance are all visible without scrolling sideways.
 */
export function ScheduleList({ rows }: { rows: ScheduleRowView[] }) {
  const { t } = useTranslation();
  const withStatus = rows.some((r) => r.status);
  return (
    <>
      <ol className="space-y-2 sm:hidden">
        {rows.map((r) => (
          <li key={r.seq} className={cn("rounded-xl border border-line bg-surface p-3", r.status === "overdue" && "border-l-4 border-l-late")}>
            <div className="flex items-start justify-between gap-2">
              <span className="font-semibold">#{r.seq} · {dmy(r.due_date)}</span>
              <span className="text-lg font-bold tabular">{money(r.installment)}</span>
            </div>
            <dl className="mt-1 grid grid-cols-3 gap-2 text-sm">
              <div><dt className="text-muted">{t("loan.principalPart")}</dt><dd className="tabular">{money(r.principal_part)}</dd></div>
              <div><dt className="text-muted">{t("loan.interestPart")}</dt><dd className="tabular">{money(r.interest_part)}</dd></div>
              <div className="text-right"><dt className="text-muted">{t("loan.balance")}</dt><dd className="tabular">{money(r.closing_balance)}</dd></div>
            </dl>
            {r.status && (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <StatusBadge status={r.status} />
                {r.status !== "paid" && r.unpaid && Number(r.unpaid) > 0 && Number(r.unpaid) < Number(r.installment) && (
                  <span className="text-sm text-muted tabular">{money(r.unpaid)}</span>
                )}
              </div>
            )}
          </li>
        ))}
      </ol>
      <div className="hidden overflow-x-auto rounded-xl border border-line bg-surface sm:block">
        <table className="w-full text-sm">
          <thead className="bg-sunken text-left">
            <tr>
              <th className="px-2 py-2">{t("loan.seq")}</th>
              <th className="px-2 py-2">{t("loan.dueDate")}</th>
              <th className="px-2 py-2 text-right">{t("loan.installment")}</th>
              <th className="px-2 py-2 text-right">{t("loan.principalPart")}</th>
              <th className="px-2 py-2 text-right">{t("loan.interestPart")}</th>
              <th className="px-2 py-2 text-right">{t("loan.balance")}</th>
              {withStatus && <th className="px-2 py-2">{t("loan.status")}</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.seq} className={cn("border-t border-line", r.status === "overdue" && "bg-late-soft/50")}>
                <td className="px-2 py-2">{r.seq}</td>
                <td className="px-2 py-2">{dmy(r.due_date)}</td>
                <td className="px-2 py-2 text-right font-semibold tabular">{money(r.installment)}</td>
                <td className="px-2 py-2 text-right tabular">{money(r.principal_part)}</td>
                <td className="px-2 py-2 text-right tabular">{money(r.interest_part)}</td>
                <td className="px-2 py-2 text-right tabular">{money(r.closing_balance)}</td>
                {withStatus && (
                  <td className="px-2 py-2">
                    {r.status && <StatusBadge status={r.status} />}
                    {r.status !== "paid" && r.unpaid && Number(r.unpaid) > 0 && Number(r.unpaid) < Number(r.installment) && (
                      <span className="ml-1 text-xs text-muted tabular">{money(r.unpaid)}</span>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
