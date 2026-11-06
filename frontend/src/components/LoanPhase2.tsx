import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "@/api/client";
import type { Schemas } from "@/api/client";
import type { AppSettings } from "@/api/types";
import { MoneyInput } from "@/components/MoneyInput";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/field";
import { Segmented } from "@/components/ui/segmented";
import { KeyValue } from "@/components/ui/states";
import { useDebounced } from "@/hooks/useOnline";
import { errorMessage } from "@/i18n";
import { dmy, money } from "@/lib/format";
import { newKey } from "@/lib/utils";

// Phase 2 on the loan page: part payment with a new schedule, charges after the loan is given,
// waivers, and the history of part payments.

type Fee = Schemas["FeeOut"];
type Resched = Schemas["RescheduleOut"];
type PrepayPreview = Schemas["PrepayPreviewOut"];
type FeeKind = "bounce" | "seizure" | "legal" | "valuation" | "insurance" | "other";

function useDone(onClose: () => void) {
  const qc = useQueryClient();
  return async () => {
    await qc.invalidateQueries();
    onClose();
  };
}

export function PrepaySheet({ loanId, interestOnly, onClose }: { loanId: string; interestOnly: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const [amount, setAmount] = useState("");
  const [mode, setMode] = useState<"reduce_emi" | "reduce_term">("reduce_emi");
  const [key] = useState(() => newKey("prepay"));
  const done = useDone(onClose);
  const q = useDebounced(amount && Number(amount) > 0 ? { amount, mode } : null, 200);
  const pv = useQuery({ queryKey: ["prepay", loanId, q], enabled: !!q, retry: false,
    queryFn: () => api.get<PrepayPreview>(`/loans/${loanId}/prepay`, q ?? {}) });
  const run = useMutation({
    mutationFn: () => api.post(`/loans/${loanId}/prepay`, { amount, mode_of_reschedule: mode, idempotency_key: key }),
    onSuccess: done,
  });
  const p = pv.data;
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={t("prepay.title")} description={t("prepay.intro")}
      footer={<>
        <Button variant="outline" onClick={onClose}>{t("app.cancel")}</Button>
        <Button variant="paid" loading={run.isPending} disabled={!p || pv.isFetching} onClick={() => run.mutate()}>
          {t("prepay.confirm", { amount: money(amount || "0") })}
        </Button>
      </>}>
      <div className="space-y-3">
        <Field label={t("prepay.amount")}>{(id) => <MoneyInput id={id} value={amount} onChange={setAmount} autoFocus />}</Field>
        {!interestOnly && (
          <Segmented value={mode} onChange={setMode}
            options={[{ value: "reduce_emi", label: t("prepay.reduceEmi"), hint: t("prepay.reduceEmiHint") },
              { value: "reduce_term", label: t("prepay.reduceTerm"), hint: t("prepay.reduceTermHint") }]} />
        )}
        {pv.error && <p role="alert" className="field-error">{errorMessage(pv.error)}</p>}
        {p && (
          <dl aria-live="polite">
            {Number(p.dues) > 0 && <KeyValue label={t("prepay.dues")} value={money(p.dues)} />}
            <KeyValue label={t("prepay.extra")} value={money(p.extra)} />
            <KeyValue label={t("prepay.principal")} value={`${money(p.principal_before)} → ${money(p.principal_after)}`} />
            <KeyValue label={t("loan.installment")} value={`${money(p.old_installment)} → ${money(p.new_installment)}`} strong />
            <KeyValue label={t("loan.installments")} value={`${p.old_count} → ${p.new_count}`} />
            <KeyValue label={t("loan.maturity")} value={`${dmy(p.old_maturity)} → ${dmy(p.new_maturity)}`} />
            <KeyValue label={t("prepay.saved")} value={money(p.interest_saved)} strong />
          </dl>
        )}
        {run.error && <p role="alert" className="field-error">{errorMessage(run.error)}</p>}
      </div>
    </Sheet>
  );
}

export function FeeSheet({ loanId, settings, onClose }: { loanId: string; settings?: AppSettings; onClose: () => void }) {
  const { t } = useTranslation();
  const [kind, setKind] = useState<FeeKind>("bounce");
  const [amount, setAmount] = useState(settings?.bounce_charge_default && Number(settings.bounce_charge_default) > 0
    ? settings.bounce_charge_default : "");
  const [label, setLabel] = useState("");
  const [note, setNote] = useState("");
  const done = useDone(onClose);
  const run = useMutation({
    mutationFn: () => api.post(`/loans/${loanId}/fees`, { kind, amount, label: kind === "other" ? label : null, note: note || null }),
    onSuccess: done,
  });
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={t("fee.addTitle")} description={t("fee.addIntro")}
      footer={<>
        <Button variant="outline" onClick={onClose}>{t("app.cancel")}</Button>
        <Button loading={run.isPending} disabled={!(Number(amount) > 0) || (kind === "other" && !label.trim())}
          onClick={() => run.mutate()}>{t("fee.add")}</Button>
      </>}>
      <div className="space-y-3">
        <Field label={t("charge.kind")}>
          {(id) => (
            <Select id={id} value={kind} onChange={(e) => setKind(e.target.value as FeeKind)}>
              {(["bounce", "seizure", "legal", "valuation", "insurance", "other"] as const).map((k) => (
                <option key={k} value={k}>{t(`fee.${k}`)}</option>
              ))}
            </Select>
          )}
        </Field>
        {kind === "other" && <Field label={t("charge.label")}>{(id) => <Input id={id} value={label} onChange={(e) => setLabel(e.target.value)} />}</Field>}
        <Field label={t("charge.amount")}>{(id) => <MoneyInput id={id} value={amount} onChange={setAmount} />}</Field>
        <Field label={t("fee.note")} optional={t("app.optional")}>{(id) => <Input id={id} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
        {run.error && <p role="alert" className="field-error">{errorMessage(run.error)}</p>}
      </div>
    </Sheet>
  );
}

/** Waive a charge (``feeId``) or the late fee (no ``feeId``), all or part, with a reason. */
export function WaiveSheet({ loanId, feeId, due, onClose }: { loanId: string; feeId?: string; due: string; onClose: () => void }) {
  const { t } = useTranslation();
  const [amount, setAmount] = useState(due);
  const [reason, setReason] = useState("");
  const done = useDone(onClose);
  const run = useMutation({
    mutationFn: () => api.post(feeId ? `/fees/${feeId}/waive` : `/loans/${loanId}/waive-late-fee`,
      { amount: amount || null, reason }),
    onSuccess: done,
  });
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={feeId ? t("fee.waiveTitle") : t("fee.waiveLateTitle")}
      description={t("fee.waiveIntro", { amount: money(due) })}
      footer={<>
        <Button variant="outline" onClick={onClose}>{t("app.cancel")}</Button>
        <Button loading={run.isPending} disabled={reason.trim().length < 3 || !(Number(amount) > 0)} onClick={() => run.mutate()}>
          {t("fee.waiveConfirm", { amount: money(amount || "0") })}
        </Button>
      </>}>
      <div className="space-y-3">
        <Field label={t("fee.waiveAmount")}>{(id) => <MoneyInput id={id} value={amount} onChange={setAmount} />}</Field>
        <Field label={t("fee.reason")}>{(id) => <Input id={id} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
        {run.error && <p role="alert" className="field-error">{errorMessage(run.error)}</p>}
      </div>
    </Sheet>
  );
}

export function FeesCard({ fees, canWaive, onWaive }: { fees: Fee[]; canWaive: boolean; onWaive: (fee: Fee) => void }) {
  const { t } = useTranslation();
  if (!fees.length) return null;
  return (
    <section className="card p-4">
      <h2 className="mb-1 text-lg">{t("fee.title")}</h2>
      <ul className="divide-y divide-line">
        {fees.map((f) => (
          <li key={f.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <div className="min-w-0">
              <p className="font-semibold">{f.kind === "other" ? f.label : t(`fee.${f.kind}`)} · {money(f.amount)}</p>
              <p className="text-sm text-muted">
                {dmy(f.charged_on)}
                {Number(f.paid) > 0 && ` · ${t("fee.paid", { amount: money(f.paid) })}`}
                {Number(f.waived) > 0 && ` · ${t("fee.waived", { amount: money(f.waived) })}`}
                {f.note && ` · ${f.note}`}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className={Number(f.due) > 0 ? "font-bold text-late tabular" : "text-paid tabular"}>
                {Number(f.due) > 0 ? t("fee.due", { amount: money(f.due) }) : t("status.paid")}
              </span>
              {canWaive && Number(f.due) > 0 && <Button size="sm" variant="outline" onClick={() => onWaive(f)}>{t("fee.waive")}</Button>}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ReschedulesCard({ items }: { items: Resched[] }) {
  const { t } = useTranslation();
  if (!items.length) return null;
  return (
    <section className="card p-4">
      <h2 className="mb-1 text-lg">{t("prepay.history")}</h2>
      <ul className="divide-y divide-line">
        {items.map((r, i) => (
          <li key={i} className="py-2 text-sm">
            <p className="font-semibold">{dmy(r.paid_on)} · {t("prepay.extra")} {money(r.extra)} · {t(r.mode === "reduce_emi" ? "prepay.reduceEmi" : "prepay.reduceTerm")}</p>
            <p className="text-muted">
              {t("loan.installment")} {money(r.old_installment)} → {money(r.new_installment)} · {r.old_count} → {r.new_count} ·{" "}
              {t("prepay.saved")} {money(r.interest_saved)}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
