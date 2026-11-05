import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, FileText, MessageCircle, Pencil, Phone, Plus } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, openFile } from "@/api/client";
import type { AppSettings, BorrowerDetail, LoanListItem } from "@/api/types";
import { ConfirmSheet } from "@/components/Confirm";
import { Documents } from "@/components/Documents";
import { Button } from "@/components/ui/button";
import { Card, EmptyState, ErrorState, KeyValue, ListSkeleton } from "@/components/ui/states";
import { StatusBadge } from "@/components/ui/status";
import { useAuth } from "@/hooks/useAuth";
import { errorMessage, useLang } from "@/i18n";
import { displayName, dmy, money } from "@/lib/format";

export function BorrowerDetailPage() {
  const { id = "" } = useParams();
  const { t } = useTranslation();
  const lang = useLang();
  const { isOwner } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [revealed, setRevealed] = useState<string | null>(null);
  const [erasing, setErasing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const b = useQuery({ queryKey: ["borrower", id], queryFn: () => api.get<BorrowerDetail>(`/borrowers/${id}`) });
  const loans = useQuery({ queryKey: ["borrower-loans", id], queryFn: () => api.get<LoanListItem[]>(`/borrowers/${id}/loans`) });
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.get<AppSettings>("/settings") });
  const reveal = useMutation({
    mutationFn: () => api.post<{ aadhaar: string }>(`/borrowers/${id}/reveal-aadhaar`),
    onSuccess: (r) => {
      setRevealed(r.aadhaar.replace(/(\d{4})(?=\d)/g, "$1 "));
      setTimeout(() => setRevealed(null), 30_000);
    },
  });
  const consent = useMutation({
    mutationFn: () => api.post(`/borrowers/${id}/consents`, { given: true, method: "verbal", language: b.data?.preferred_language }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["borrower", id] }),
  });
  if (b.isLoading) return <ListSkeleton rows={3} />;
  if (b.isError || !b.data) return <ErrorState error={b.error} onRetry={() => void b.refetch()} />;
  const d = b.data;
  const exportData = async () => {
    const data = await api.get<unknown>(`/borrowers/${id}/export`);
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${d.code}.json`;
    a.click();
  };
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl">{displayName(lang, d.name_en, d.name_ta)}</h1>
          {d.name_en && d.name_ta && <p className="text-muted">{lang === "ta" ? d.name_en : d.name_ta}</p>}
          <p className="text-muted">{d.code}{d.relation_name ? ` · ${d.relation_name}` : ""}</p>
          <div className="mt-1 flex flex-wrap gap-1">
            <StatusBadge status={d.status} />
            {d.profile_incomplete && <StatusBadge status="incomplete" />}
          </div>
        </div>
        <div className="flex gap-2">
          <Link to={`/borrowers/${id}/edit`}><Button variant="outline"><Pencil className="h-4 w-4" aria-hidden />{t("app.edit")}</Button></Link>
          <Link to={`/loans/new?borrower=${id}`}><Button><Plus className="h-4 w-4" aria-hidden />{t("nav.giveLoan")}</Button></Link>
        </div>
      </div>
      {d.profile_incomplete && <p className="rounded-xl bg-due-soft p-3 font-semibold text-due">{t("borrower.incomplete")}</p>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card><p className="text-sm text-muted">{t("borrower.outstanding")}</p><p className="text-lg font-bold tabular">{money(d.totals.outstanding)}</p></Card>
        <Card className={Number(d.totals.overdue_amount) > 0 ? "border-l-4 border-l-late" : ""}>
          <p className="text-sm text-muted">{t("borrower.overdue")}</p>
          <p className="text-lg font-bold tabular">{money(d.totals.overdue_amount)}</p>
          {d.totals.overdue_days > 0 && <p className="text-sm text-late">{t("dues.overdueDays", { count: d.totals.overdue_days })}</p>}
        </Card>
        <Card><p className="text-sm text-muted">{t("borrower.lastPayment")}</p><p className="font-semibold">{d.totals.last_payment_on ? dmy(d.totals.last_payment_on) : t("dues.neverPaid")}</p></Card>
        <Card><p className="text-sm text-muted">{t("borrower.activeLoans")}</p><p className="text-lg font-bold">{d.totals.active_loans}</p></Card>
      </div>

      {/* Laptop: profile, consent and privacy on the left; loans, documents and statement on the right. */}
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(19rem,1fr)_minmax(0,2fr)]">
        <div className="space-y-4">
          <Card>
            <dl>
              <KeyValue label={t("borrower.phone")} value={d.phone ? (
                <span className="inline-flex flex-wrap items-center justify-end gap-2">{d.phone}
                  <a href={`tel:+91${d.phone}`} aria-label={t("dues.call")} className="inline-flex min-h-touch min-w-touch items-center justify-center rounded-lg border border-line"><Phone className="h-4 w-4" aria-hidden /></a>
                  <a href={`https://wa.me/91${d.phone}`} target="_blank" rel="noopener noreferrer" aria-label={t("dues.whatsapp")} className="inline-flex min-h-touch min-w-touch items-center justify-center rounded-lg border border-line"><MessageCircle className="h-4 w-4" aria-hidden /></a>
                </span>) : "—"} />
              {d.alt_phone && <KeyValue label={t("borrower.altPhone")} value={d.alt_phone} />}
              <KeyValue label={t("borrower.aadhaar")} value={
                <span className="inline-flex items-center gap-2 tabular">
                  {revealed ?? d.aadhaar_masked ?? "—"}
                  {isOwner && d.aadhaar_masked && (
                    <Button size="sm" variant="ghost" loading={reveal.isPending}
                      onClick={() => (revealed ? setRevealed(null) : reveal.mutate())}
                      aria-label={revealed ? t("borrower.hide") : t("borrower.reveal")}>
                      {revealed ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
                    </Button>
                  )}
                </span>} />
              <KeyValue label={t("borrower.address")} value={<span className="whitespace-pre-line">{d.address}</span>} />
              <KeyValue label={t("borrower.language")} value={d.preferred_language === "ta" ? "தமிழ்" : "English"} />
              {d.guarantors.map((g) => (
                <KeyValue key={g.id} label={t("borrower.guarantor")} value={`${g.name}${g.relation ? ` (${g.relation})` : ""}${g.phone ? ` · ${g.phone}` : ""}`} />
              ))}
              {d.notes && <KeyValue label={t("borrower.notes")} value={<span className="whitespace-pre-line">{d.notes}</span>} />}
            </dl>
            {reveal.error && <p className="field-error">{errorMessage(reveal.error)}</p>}
          </Card>

          <Card>
            <h2 className="mb-2 text-lg">{t("borrower.consents")}</h2>
            {d.consents.length === 0 ? (
              <div className="space-y-2">
                <p className="text-due">{t("borrower.noConsent")}</p>
                <Button variant="secondary" loading={consent.isPending} onClick={() => consent.mutate()}>{t("borrower.recordConsent")}</Button>
              </div>
            ) : (
              <ul className="space-y-1 text-sm">
                {d.consents.map((c) => (
                  <li key={c.id}>{dmy(String(c.created_at))} · {c.method === "signed" ? t("borrower.consentSigned") : t("borrower.consentVerbal")} · {c.language === "ta" ? "தமிழ்" : "English"} · {c.notice_version}</li>
                ))}
              </ul>
            )}
          </Card>

          {isOwner && (
            <Card>
              <h2 className="mb-2 text-lg">{t("borrower.privacy")}</h2>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={() => void exportData()}>{t("borrower.export")}</Button>
                <Button variant="outline" onClick={() => setErasing(true)}>{t("borrower.erase")}</Button>
                <Button variant="ghost" className="text-late" onClick={() => setDeleting(true)}>{t("app.delete")}</Button>
              </div>
            </Card>
          )}
        </div>
        <div className="min-w-0 space-y-4">
          <section className="space-y-2">
            <h2 className="text-lg">{t("borrower.loans")}</h2>
            {loans.data && loans.data.length === 0 && <EmptyState text={t("borrower.noLoans")} />}
            {loans.data?.map((l) => (
              <Link key={l.id} to={`/loans/${l.id}`} className="card flex items-center justify-between gap-3 p-3 hover:bg-sunken">
                <div>
                  <p className="font-semibold">{l.loan_no}</p>
                  <p className="text-sm text-muted">{money(l.principal)} · {t(`method.${l.method}`)} · {dmy(l.disbursal_date)}</p>
                </div>
                <div className="text-right">
                  <StatusBadge status={l.status} />
                  <p className="mt-1 tabular">{money(l.outstanding)}</p>
                </div>
              </Link>
            ))}
          </section>

          <Card><Documents ownerType="borrower" ownerId={id} maxMb={settings.data?.max_upload_mb} /></Card>

          <Card>
            <h2 className="mb-2 text-lg">{t("borrower.statement")}</h2>
            <div className="flex flex-wrap gap-2">
              {(["ta", "en"] as const).map((l) => (
                <Button key={l} variant="outline" onClick={() => void openFile(`/borrowers/${id}/statement.pdf`, { lang: l })}>
                  <FileText className="h-4 w-4" aria-hidden />{l === "ta" ? "தமிழ்" : "English"}
                </Button>
              ))}
            </div>
          </Card>

        </div>
      </div>

      <ConfirmSheet open={erasing} onOpenChange={setErasing} title={t("borrower.erase")} body={t("borrower.eraseConfirm")}
        confirmLabel={t("borrower.erase")} danger onConfirm={async () => {
          await api.post(`/borrowers/${id}/erase`);
          await qc.invalidateQueries();
        }} />
      <ConfirmSheet open={deleting} onOpenChange={setDeleting} title={t("app.delete")} body={t("borrower.deleteConfirm")}
        confirmLabel={t("app.delete")} danger onConfirm={async () => {
          await api.delete(`/borrowers/${id}`);
          await qc.invalidateQueries({ queryKey: ["borrowers"] });
          navigate("/borrowers");
        }} />
    </div>
  );
}
