import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/states";

interface Entry { id: string; at: string; user: string | null; action: string; entity_type: string | null;
  entity_id: string | null; changes: Record<string, unknown>; ip: string | null }

export function AuditPage() {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const q = useQuery({ queryKey: ["audit", page], queryFn: () => api.get<{ items: Entry[] }>("/audit", { page, page_size: 50 }) });
  return (
    <div className="space-y-4">
      <h1 className="text-2xl">{t("audit.title")}</h1>
      {q.isLoading && <ListSkeleton />}
      {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
      {q.data && q.data.items.length === 0 && <EmptyState text={t("audit.empty")} />}
      <ul className="space-y-2">
        {q.data?.items.map((e) => (
          <li key={e.id} className="card p-3 text-sm">
            <div className="flex flex-wrap justify-between gap-2">
              <span className="font-semibold">{e.action}</span>
              <time className="text-muted">{new Date(e.at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}</time>
            </div>
            <p className="text-muted">{e.user ?? "—"}{e.entity_type ? ` · ${e.entity_type}` : ""}{e.ip ? ` · ${e.ip}` : ""}</p>
            {Object.keys(e.changes).length > 0 && (
              <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded-lg bg-sunken p-2 text-xs">{JSON.stringify(e.changes, null, 1)}</pre>
            )}
          </li>
        ))}
      </ul>
      <div className="flex justify-between">
        <Button variant="outline" disabled={page === 1} onClick={() => setPage((p) => p - 1)}>{t("app.back")}</Button>
        <span className="self-center text-muted">{t("app.page", { page })}</span>
        <Button variant="outline" disabled={(q.data?.items.length ?? 0) < 50} onClick={() => setPage((p) => p + 1)}>{t("app.next")}</Button>
      </div>
    </div>
  );
}
