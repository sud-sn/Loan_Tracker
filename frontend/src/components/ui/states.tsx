import { AlertCircle, Inbox } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { errorMessage } from "@/i18n";
import { cn } from "@/lib/utils";

import { Button } from "./button";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton h-4", className)} aria-hidden />;
}

export function ListSkeleton({ rows = 4 }: { rows?: number }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-3" role="status" aria-label={t("app.loading")}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="card space-y-2 p-4">
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="w-1/3" />
        </div>
      ))}
    </div>
  );
}

export function EmptyState({ text, action }: { text: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-line p-6 text-center text-muted">
      <Inbox className="h-8 w-8" aria-hidden />
      <p>{text}</p>
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation();
  return (
    <div role="alert" className="flex flex-col items-start gap-3 rounded-2xl border border-late/30 bg-late-soft p-4 text-late">
      <div className="flex items-start gap-2">
        <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
        <div>
          <p className="font-semibold">{t("app.errorTitle")}</p>
          <p className="text-ink">{errorMessage(error)}</p>
        </div>
      </div>
      {onRetry && <Button variant="outline" onClick={onRetry}>{t("app.retry")}</Button>}
    </div>
  );
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <section className={cn("card p-4", className)}>{children}</section>;
}

export function KeyValue({ label, value, strong }: { label: ReactNode; value: ReactNode; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line/70 py-2 last:border-0">
      <dt className="text-muted">{label}</dt>
      <dd className={cn("text-right tabular", strong && "font-semibold")}>{value}</dd>
    </div>
  );
}
