import { AlertTriangle, Ban, CheckCircle2, Circle, Clock, RefreshCw, XCircle } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

const STYLES: Record<string, { cls: string; Icon: typeof Clock }> = {
  paid: { cls: "bg-paid-soft text-paid", Icon: CheckCircle2 },
  closed: { cls: "bg-paid-soft text-paid", Icon: CheckCircle2 },
  due_today: { cls: "bg-due-soft text-due", Icon: Clock },
  due_soon: { cls: "bg-due-soft text-due", Icon: Clock },
  partially_paid: { cls: "bg-due-soft text-due", Icon: Clock },
  overdue: { cls: "bg-late-soft text-late", Icon: AlertTriangle },
  written_off: { cls: "bg-sunken text-muted", Icon: XCircle },
  blocked: { cls: "bg-late-soft text-late", Icon: Ban },
  incomplete: { cls: "bg-due-soft text-due", Icon: AlertTriangle },
  upcoming: { cls: "bg-sunken text-muted", Icon: Circle },
  active: { cls: "bg-brand-soft text-brand", Icon: Circle },
  rescheduled: { cls: "bg-sunken text-muted", Icon: RefreshCw },
};

/** Status is never colour alone: always an icon and a word (PRD section 10). */
export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const { t } = useTranslation();
  const s = STYLES[status] ?? STYLES.upcoming;
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-sm font-semibold", s.cls, className)}>
      <s.Icon className="h-4 w-4 shrink-0" aria-hidden />
      {t(`status.${status}`)}
    </span>
  );
}
