import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, HandCoins, MessageCircle, Phone, Printer, Share2, Undo2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, openFile, shareFile } from "@/api/client";
import type { AppSettings, LoanDetail, Payment, Reminder, Settlement } from "@/api/types";
import { ConfirmSheet } from "@/components/Confirm";
import { Documents } from "@/components/Documents";
import { LoanSummaryExtras, SecurityCard } from "@/components/LoanExtras";
import { FeeSheet, FeesCard, PrepaySheet, ReschedulesCard, WaiveSheet } from "@/components/LoanPhase2";
import { DateInput } from "@/components/DateInput";
import { MoneyInput } from "@/components/MoneyInput";
import { ScheduleList } from "@/components/ScheduleList";
import { useQuickActions } from "@/components/QuickActions";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/field";
import { Card, ErrorState, KeyValue, ListSkeleton } from "@/components/ui/states";
import { StatusBadge } from "@/components/ui/status";
import { useDebounced } from "@/hooks/useOnline";
import { useAuth } from "@/hooks/useAuth";
import { errorMessage, useLang } from "@/i18n";
import { displayName, dmy, money, todayIST } from "@/lib/format";
import { cn, newKey } from "@/lib/utils";

export function LoanDetailPage() {
  const { id = "" } = useParams();
  const { t } = useTranslation();
  const lang = useLang();
  const { isOwner } = useAuth();
  const qa = useQuickActions();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [reversing, setReversing] = useState<Payment | null>(null);
  const [settling, setSettling] = useState(false);
  const [prepaying, setPrepaying] = useState(false);
  const [addingFee, setAddingFee] = useState(false);
  const [waiving, setWaiving] = useState<{ feeId?: string; due: string } | null>(null);
  const [writingOff, setWritingOff] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const loan = useQuery({ queryKey: ["loan", id], queryFn: () => api.get<LoanDetail>(`/loans/${id}`) });
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.get<AppSettings>("/settings") });
  const reminder = useMutation({
    mutationFn: () => api.get<Reminder>(`/loans/${id}/reminder`),
    onSuccess: (r) => r.whatsapp_url && window.open(r.whatsapp_url, "_blank", "noopener"),
  });
  if (loan.isLoading) return <ListSkeleton rows={3} />;
  if (loan.isError || !loan.data) return <ErrorState error={loan.error} onRetry={() => void loan.refetch()} />;
  const l = loan.data;
  const s = l.summary;
  const active = l.stored_status === "active";
  const dueNow = Number(s.overdue_amount) + Number(s.due_today_amount);
  const period = t(`period.${l.frequency}`);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl">{l.loan_no}</h1>
          <Link to={`/borrowers/${l.borrower.id}`} className="font-semibold text-brand underline">
            {displayName(lang, l.borrower.name_en, l.borrower.name_ta)} · {l.borrower.code}
          </Link>
          <div className="mt-1"><StatusBadge status={s.status} /></div>
          {l.closed_on && <p className="text-sm text-muted">{l.closed_reason === "settled_early" ? t("loan.settledEarly") : t("loan.closedOn", { date: dmy(l.closed_on) })}</p>}
        </div>
        {active && (
          <Button variant="paid" size="lg" onClick={() => qa.receivePayment(l.id, dueNow > 0 ? dueNow.toFixed(2) : undefined)}>
            <HandCoins className="h-5 w-5" aria-hidden />{t("dues.recordPayment")}
          </Button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card><p className="text-sm text-muted">{t("loan.outstanding")}</p><p className="text-lg font-bold tabular">{money(s.total_outstanding)}</p></Card>
        <Card className={Number(s.overdue_amount) > 0 ? "border-l-4 border-l-late" : ""}>
          <p className="text-sm text-muted">{t("loan.overdueAmount")}</p>
          <p className="text-lg font-bold tabular">{money(s.overdue_amount)}</p>
          {s.overdue_days > 0 && <p className="text-sm text-late">{t("dues.overdueDays", { count: s.overdue_days })}</p>}
        </Card>
        <Card><p className="text-sm text-muted">{t("loan.nextDue")}</p><p className="font-semibold">{s.next_due_date ? `${dmy(s.next_due_date)} · ${money(s.next_due_amount)}` : "—"}</p></Card>
        <Card><p className="text-sm text-muted">{t("loan.paid")}</p><p className="text-lg font-bold tabular">{money(s.paid_total)}</p></Card>
      </div>

      {/* Laptop: details and actions on the left (stays in view), schedule and payments on the right. */}
      <div className="grid items-start gap-6 lg:grid-cols-[clamp(19rem,32%,34rem)_minmax(0,1fr)]">
        <aside className="space-y-4 lg:sticky lg:top-24 lg:max-h-[calc(100dvh-7rem)] lg:overflow-y-auto lg:pr-1">
          <Card>
            <h2 className="mb-1 text-lg">{t("loan.summary")}</h2>
            <dl>
              <KeyValue label={t("loan.principal")} value={money(l.principal)} />
              <KeyValue label={t("loan.rate")} value={`${Number(l.rate)} ${t(`rateBasis.${l.rate_basis}`)}`} />
              <KeyValue label={t("loan.method")} value={t(`method.${l.method}`)} />
              <KeyValue label={t("loan.frequency")} value={t(`frequency.${l.frequency}`)} />
              {l.fixed_installment && <KeyValue label={t("loan.fixedAmount", { period })} value={money(l.fixed_installment)} />}
              <KeyValue label={t("loan.installment")} value={money(l.installment_amount)} />
              <KeyValue label={t("loan.installments")} value={l.installments} />
              <KeyValue label={t("loan.totalInterest")} value={money(l.total_interest)} />
              <KeyValue label={t("loan.disbursalDate")} value={`${dmy(l.disbursal_date)} · ${t(`mode.${l.disbursal_mode}`)}`} />
              <KeyValue label={t("loan.maturity")} value={dmy(l.maturity_date)} />
              <LoanSummaryExtras l={l} />
              {Number(s.penalty_outstanding) > 0 && <KeyValue label={t("payment.penalty")} value={money(s.penalty_outstanding)} />}
              {l.purpose && <KeyValue label={t("loan.purpose")} value={l.purpose} />}
            </dl>
          </Card>
          <SecurityCard security={l.security} />
          <FeesCard fees={l.fees} canWaive={!!isOwner && active} onWaive={(f) => setWaiving({ feeId: f.id, due: f.due })} />
          <ReschedulesCard items={l.reschedules} />
          <div className="flex flex-wrap gap-2 lg:grid lg:grid-cols-2">
            {l.borrower.phone && (
              <>
                <a href={`tel:+91${l.borrower.phone}`} className="inline-flex min-h-touch items-center gap-2 rounded-xl border border-line bg-surface px-4 font-semibold">
                  <Phone className="h-5 w-5" aria-hidden />{t("dues.call")}
                </a>
                <Button variant="outline" loading={reminder.isPending} onClick={() => reminder.mutate()}>
                  <MessageCircle className="h-5 w-5" aria-hidden />{t("dues.whatsapp")}
                </Button>
              </>
            )}
            {(["ta", "en"] as const).map((pl) => (
              <Button key={pl} variant="outline" onClick={() => void openFile(`/loans/${id}/summary.pdf`, { lang: pl })}>
                <Printer className="h-5 w-5" aria-hidden />{t("loan.printSummary")} · {pl === "ta" ? "தமிழ்" : "EN"}
              </Button>
            ))}
          </div>
          {isOwner && active && (
            <Card>
              <h2 className="mb-2 text-lg">{t("loan.actions")}</h2>
              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" onClick={() => setPrepaying(true)}>{t("prepay.button")}</Button>
                <Button variant="secondary" onClick={() => setSettling(true)}>{t("loan.settle")}</Button>
                <Button variant="outline" onClick={() => setAddingFee(true)}>{t("fee.add")}</Button>
                {Number(s.penalty_outstanding) > 0 && (
                  <Button variant="outline" onClick={() => setWaiving({ due: s.penalty_outstanding })}>{t("fee.waiveLate")}</Button>
                )}
                <Button variant="outline" onClick={() => setWritingOff(true)}>{t("loan.writeOff")}</Button>
                {l.payments.length === 0 && <Button variant="ghost" className="text-late" onClick={() => setDeleting(true)}>{t("app.delete")}</Button>}
              </div>
            </Card>
          )}
          <Card><Documents ownerType="loan" ownerId={id} maxMb={settings.data?.max_upload_mb} /></Card>
        </aside>
        <div className="min-w-0 space-y-6">
          <section className="space-y-2">
            <h2 className="text-lg">{t("loan.schedule")}</h2>
            <ScheduleList rows={l.schedule} />
          </section>
          <section className="space-y-2">
            <h2 className="text-lg">{t("loan.payments")}</h2>
            {l.payments.length === 0 && <p className="text-muted">{t("loan.noPayments")}</p>}
            <ul className="space-y-2">
              {l.payments.map((p) => (
                <li key={p.id} className={cn("card p-3", p.kind === "reversal" && "border-l-4 border-l-late")}>
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="font-semibold">{p.receipt_no} · {dmy(p.paid_on)}</p>
                      <p className="text-sm text-muted">
                        {p.kind === "reversal" ? t("payment.reversal") : p.kind === "settlement" ? t("payment.settlement") : t(`mode.${p.mode}`)}
                        {p.reversal_reason ? ` · ${p.reversal_reason}` : ""}
                        {p.reversed_by_id ? ` · ${t("payment.reversed")}` : ""}
                      </p>
                      <p className="text-sm text-muted">
                        {t("payment.interest")} {money(p.interest_total)} · {t("payment.principal")} {money(p.principal_total)}
                        {Number(p.penalty_total) !== 0 && ` · ${t("payment.penalty")} ${money(p.penalty_total)}`}
                      </p>
                    </div>
                    <p className={cn("text-lg font-bold tabular", p.kind === "reversal" ? "text-late" : "text-moneyin", p.reversed_by_id && "line-through")}>
                      {p.kind === "reversal" ? "−" : ""}{money(p.amount)}
                    </p>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" onClick={() => void openFile(`/payments/${p.id}/receipt.pdf`)}>
                      <FileText className="h-4 w-4" aria-hidden />{t("payment.receipt")}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => void shareFile(`/payments/${p.id}/receipt.pdf`)}>
                      <Share2 className="h-4 w-4" aria-hidden />{t("app.share")}
                    </Button>
                    {isOwner && p.kind === "payment" && !p.reversed_by_id && l.stored_status !== "written_off" && (
                      <Button size="sm" variant="ghost" className="text-late" onClick={() => setReversing(p)}>
                        <Undo2 className="h-4 w-4" aria-hidden />{t("payment.reverse")}
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>

      <ConfirmSheet open={!!reversing} onOpenChange={(o) => !o && setReversing(null)} title={t("payment.reverseTitle")}
        body={reversing && <p>{t("payment.reverseIntro")} <b>{reversing.receipt_no} · {money(reversing.amount)}</b></p>}
        reasonLabel={t("payment.reverseReason")} confirmLabel={t("payment.reverse")} danger
        onConfirm={async (reason) => {
          await api.post(`/payments/${reversing?.id}/reverse`, { reason });
          await qc.invalidateQueries();
        }} />
      {settling && <SettleSheet loanId={id} onClose={() => setSettling(false)} />}
      {prepaying && l && <PrepaySheet loanId={id} interestOnly={l.method === "interest_only"} onClose={() => setPrepaying(false)} />}
      {addingFee && <FeeSheet loanId={id} settings={settings.data} onClose={() => setAddingFee(false)} />}
      {waiving && <WaiveSheet loanId={id} feeId={waiving.feeId} due={waiving.due} onClose={() => setWaiving(null)} />}
      {writingOff && <WriteOffSheet loanId={id} onClose={() => setWritingOff(false)} />}
      <ConfirmSheet open={deleting} onOpenChange={setDeleting} title={t("app.delete")} body={t("loan.deleteConfirm")}
        confirmLabel={t("app.delete")} danger onConfirm={async () => {
          await api.delete(`/loans/${id}`);
          await qc.invalidateQueries();
          navigate("/loans");
        }} />
    </div>
  );
}

function SettleSheet({ loanId, onClose }: { loanId: string; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [on, setOn] = useState(todayIST());
  const [rebate, setRebate] = useState<"pro_rata" | "rule_of_78" | "none">("pro_rata");
  const [charge, setCharge] = useState<string | null>(null); // null = the % from Settings
  const [key] = useState(() => newKey("settle"));
  const debouncedCharge = useDebounced(charge, 250);
  const params = { on, rebate, ...(debouncedCharge !== null && debouncedCharge !== "" ? { foreclosure_charge: debouncedCharge } : {}) };
  const fig = useQuery({ queryKey: ["settlement", loanId, params], queryFn: () => api.get<Settlement>(`/loans/${loanId}/settlement`, params) });
  const settle = useMutation({
    mutationFn: () => api.post(`/loans/${loanId}/settle`, { on, rebate, foreclosure_charge: fig.data?.foreclosure_charge,
      expected_total: fig.data?.total, idempotency_key: key }),
    onSuccess: async () => {
      await qc.invalidateQueries();
      onClose();
    },
  });
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={t("loan.settleTitle")} description={t("loan.settleIntro")}
      footer={<>
        <Button variant="outline" onClick={onClose}>{t("app.cancel")}</Button>
        <Button variant="paid" loading={settle.isPending} disabled={!fig.data} onClick={() => settle.mutate()}>
          {t("loan.settleConfirm", { amount: money(fig.data?.total) })}
        </Button>
      </>}>
      <div className="space-y-3">
        <Field label={t("loan.settleDate")}>
          {(id) => <DateInput id={id} max={todayIST()} value={on} onChange={setOn} />}
        </Field>
        <Field label={t("settle.rebate")} hint={t(`settle.rebate_${rebate}_hint`)}>
          {(id, d) => (
            <Select id={id} aria-describedby={d} value={rebate} onChange={(e) => setRebate(e.target.value as typeof rebate)}>
              {(["pro_rata", "rule_of_78", "none"] as const).map((r) => <option key={r} value={r}>{t(`settle.rebate_${r}`)}</option>)}
            </Select>
          )}
        </Field>
        <Field label={t("settle.foreclosure")} hint={fig.data ? t("settle.foreclosureHint", { percent: fig.data.foreclosure_percent }) : undefined}>
          {(id, d) => <MoneyInput id={id} describedBy={d} value={charge ?? fig.data?.foreclosure_charge ?? ""} onChange={(v) => setCharge(v)} />}
        </Field>
        {fig.error && <p className="field-error">{errorMessage(fig.error)}</p>}
        {fig.data && (
          <dl>
            <KeyValue label={t("payment.principal")} value={money(fig.data.principal)} />
            <KeyValue label={t("payment.interest")} value={money(fig.data.interest)} />
            {Number(fig.data.penalty) > 0 && <KeyValue label={t("payment.penalty")} value={money(fig.data.penalty)} />}
            <KeyValue label={t("loan.settleWaived")} value={money(fig.data.interest_waived)} />
            {Number(fig.data.charges) > 0 && <KeyValue label={t("fee.title")} value={money(fig.data.charges)} />}
            <KeyValue label={t("settle.foreclosure")} value={money(fig.data.foreclosure_charge)} />
            <KeyValue label={t("loan.settleTotal")} value={money(fig.data.total)} strong />
          </dl>
        )}
        {settle.error && <p role="alert" className="field-error">{errorMessage(settle.error)}</p>}
      </div>
    </Sheet>
  );
}

function WriteOffSheet({ loanId, onClose }: { loanId: string; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  const [amount, setAmount] = useState("");
  const [key] = useState(() => newKey("writeoff"));
  const run = useMutation({
    mutationFn: () => api.post(`/loans/${loanId}/write-off`, { reason, amount_received: amount || null, idempotency_key: key }),
    onSuccess: async () => {
      await qc.invalidateQueries();
      onClose();
    },
  });
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={t("loan.writeOffTitle")} description={t("loan.writeOffIntro")}
      footer={<>
        <Button variant="outline" onClick={onClose}>{t("app.cancel")}</Button>
        <Button variant="danger" loading={run.isPending} disabled={reason.trim().length < 3} onClick={() => run.mutate()}>
          {t("loan.writeOffConfirm")}
        </Button>
      </>}>
      <div className="space-y-3">
        <Field label={t("loan.writeOffReason")}>
          {(id) => <Input id={id} value={reason} onChange={(e) => setReason(e.target.value)} />}
        </Field>
        <Field label={t("loan.writeOffAmount")}>
          {(id) => <MoneyInput id={id} value={amount} onChange={setAmount} />}
        </Field>
        {run.error && <p role="alert" className="field-error">{errorMessage(run.error)}</p>}
      </div>
    </Sheet>
  );
}
