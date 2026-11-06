import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileCheck2, ShieldAlert, Truck } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, openFile, type Schemas } from "@/api/client";
import type { LoanDetail } from "@/api/types";
import { DateInput } from "@/components/DateInput";
import { MoneyInput } from "@/components/MoneyInput";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/field";
import { KeyValue } from "@/components/ui/states";
import { useDebounced } from "@/hooks/useOnline";
import { errorMessage, useLang } from "@/i18n";
import { displayName, dmy, money, todayIST } from "@/lib/format";
import { newKey } from "@/lib/utils";

// Phase 3 on the loan page: restructure, seizure and sale, cheques, editing and releasing the
// security, the no-dues certificate; and the insurance list on the home page.

type Cheque = Schemas["ChequeOut"];
type Security = Schemas["SecurityOut"];

function useDone(onClose: () => void) {
  const qc = useQueryClient();
  return async () => {
    await qc.invalidateQueries();
    onClose();
  };
}

function Footer({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  const { t } = useTranslation();
  return <><Button variant="outline" onClick={onClose}>{t("app.cancel")}</Button>{children}</>;
}

export function RestructureSheet({ loan, onClose }: { loan: LoanDetail; onClose: () => void }) {
  const { t } = useTranslation();
  const [holiday, setHoliday] = useState("0");
  const [extra, setExtra] = useState("0");
  const [rate, setRate] = useState("");
  const [reason, setReason] = useState("");
  const done = useDone(onClose);
  const body = { holiday: Number(holiday), extra_installments: Number(extra), new_rate: rate || null, reason: reason || "preview" };
  const q = useDebounced(body, 250);
  const pv = useQuery({ queryKey: ["restructure", loan.id, q], retry: false,
    queryFn: () => api.post<Schemas["RestructurePreviewOut"]>(`/loans/${loan.id}/restructure/preview`, q) });
  const run = useMutation({ mutationFn: () => api.post(`/loans/${loan.id}/restructure`, { ...body, reason, version: loan.version }), onSuccess: done });
  const p = pv.data;
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={t("restructure.title")} description={t("restructure.intro")}
      footer={<Footer onClose={onClose}><Button loading={run.isPending} disabled={!p || reason.trim().length < 3}
        onClick={() => run.mutate()}>{t("restructure.confirm")}</Button></Footer>}>
      <div className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={t("restructure.holiday")}>
            {(id) => <Select id={id} value={holiday} onChange={(e) => setHoliday(e.target.value)}>
              {["0", "1", "2", "3", "6"].map((v) => <option key={v} value={v}>{v}</option>)}</Select>}
          </Field>
          <Field label={t("restructure.extra")}>
            {(id) => <Select id={id} value={extra} onChange={(e) => setExtra(e.target.value)}>
              {["0", "3", "6", "12", "24"].map((v) => <option key={v} value={v}>{v}</option>)}</Select>}
          </Field>
          <Field label={t("restructure.rate")} optional={t("app.optional")}>
            {(id) => <Input id={id} inputMode="decimal" value={rate} placeholder={String(Number(loan.current_rate))}
              onChange={(e) => setRate(e.target.value.replace(/[^\d.]/g, ""))} />}
          </Field>
        </div>
        <Field label={t("fee.reason")}>{(id) => <Input id={id} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
        {pv.error && <p role="alert" className="field-error">{errorMessage(pv.error)}</p>}
        {p && (
          <dl aria-live="polite">
            <KeyValue label={t("prepay.principal")} value={money(p.principal)} />
            {Number(p.carried_interest) > 0 && <KeyValue label={t("restructure.carried")} value={money(p.carried_interest)} />}
            <KeyValue label={t("loan.installment")} value={`${money(p.old_installment)} → ${money(p.new_installment)}`} strong />
            <KeyValue label={t("loan.installments")} value={`${p.old_count} → ${p.new_count}`} />
            <KeyValue label={t("loan.maturity")} value={`${dmy(p.old_maturity)} → ${dmy(p.new_maturity)}`} />
            <KeyValue label={t("restructure.interestChange")} value={money(p.interest_change)} />
          </dl>
        )}
        {run.error && <p role="alert" className="field-error">{errorMessage(run.error)}</p>}
      </div>
    </Sheet>
  );
}

export function SeizeSheet({ loanId, onClose }: { loanId: string; onClose: () => void }) {
  const { t } = useTranslation();
  const [on, setOn] = useState(todayIST());
  const [note, setNote] = useState("");
  const [charge, setCharge] = useState("");
  const done = useDone(onClose);
  const run = useMutation({ mutationFn: () => api.post(`/loans/${loanId}/seize`, { on, note: note || null, charge: charge || null }), onSuccess: done });
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={t("recovery.seizeTitle")} description={t("recovery.seizeIntro")}
      footer={<Footer onClose={onClose}><Button variant="danger" loading={run.isPending} onClick={() => run.mutate()}>{t("recovery.seize")}</Button></Footer>}>
      <div className="space-y-3">
        <Field label={t("recovery.on")}>{(id) => <DateInput id={id} max={todayIST()} value={on} onChange={setOn} />}</Field>
        <Field label={t("recovery.charge")} optional={t("app.optional")}>{(id) => <MoneyInput id={id} value={charge} onChange={setCharge} />}</Field>
        <Field label={t("fee.note")} optional={t("app.optional")}>{(id) => <Input id={id} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
        {run.error && <p role="alert" className="field-error">{errorMessage(run.error)}</p>}
      </div>
    </Sheet>
  );
}

export function SellSheet({ loanId, onClose }: { loanId: string; onClose: () => void }) {
  const { t } = useTranslation();
  const [price, setPrice] = useState("");
  const [expenses, setExpenses] = useState("");
  const [key] = useState(() => newKey("sell"));
  const [result, setResult] = useState<Schemas["SellOut"] | null>(null);
  const qc = useQueryClient();
  const run = useMutation({
    mutationFn: () => api.post<Schemas["SellOut"]>(`/loans/${loanId}/sell`, { sale_price: price, expenses: expenses || "0", idempotency_key: key }),
    onSuccess: async (r) => { setResult(r); await qc.invalidateQueries(); },
  });
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={t("recovery.sellTitle")} description={t("recovery.sellIntro")}
      footer={result ? <Button onClick={onClose}>{t("app.close")}</Button>
        : <Footer onClose={onClose}><Button loading={run.isPending} disabled={!(Number(price) > 0)} onClick={() => run.mutate()}>{t("recovery.sell")}</Button></Footer>}>
      {result ? (
        <dl aria-live="polite">
          <KeyValue label={t("recovery.paidToLoan")} value={money(result.paid_to_loan)} />
          {Number(result.refund) > 0 && <KeyValue label={t("recovery.refund")} value={money(result.refund)} strong />}
          {Number(result.shortfall) > 0 && <KeyValue label={t("recovery.shortfall")} value={money(result.shortfall)} strong />}
          <p className="mt-2 font-semibold">{result.closed ? t("recovery.closed") : t("recovery.stillOwed")}</p>
        </dl>
      ) : (
        <div className="space-y-3">
          <Field label={t("recovery.price")}>{(id) => <MoneyInput id={id} value={price} onChange={setPrice} autoFocus />}</Field>
          <Field label={t("recovery.expenses")} optional={t("app.optional")}>{(id) => <MoneyInput id={id} value={expenses} onChange={setExpenses} />}</Field>
          {run.error && <p role="alert" className="field-error">{errorMessage(run.error)}</p>}
        </div>
      )}
    </Sheet>
  );
}

export function RecoveryBanner({ loan }: { loan: LoanDetail }) {
  const { t } = useTranslation();
  if (loan.recovery_status === "none") return null;
  return (
    <p role="status" className="flex items-start gap-2 rounded-xl bg-late-soft p-3 font-semibold text-late">
      <Truck className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
      <span className="min-w-0">
        {loan.recovery_status === "seized" ? t("recovery.seizedOn", { date: dmy(loan.seized_on ?? "") }) : t("recovery.sold")}
        {loan.seizure_note ? ` · ${loan.seizure_note}` : ""}
        {loan.refunds.map((r, i) => <span key={i}> · {t("recovery.refund")} {money(r.amount)}</span>)}
      </span>
    </p>
  );
}

export function ChequeSheet({ loanId, onClose }: { loanId: string; onClose: () => void }) {
  const { t } = useTranslation();
  const [no, setNo] = useState("");
  const [bank, setBank] = useState("");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(todayIST());
  const done = useDone(onClose);
  const run = useMutation({ mutationFn: () => api.post(`/loans/${loanId}/cheques`, { cheque_no: no, bank: bank || null, amount, cheque_date: date }), onSuccess: done });
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={t("cheque.addTitle")} description={t("cheque.intro")}
      footer={<Footer onClose={onClose}><Button loading={run.isPending} disabled={!no.trim() || !(Number(amount) > 0)} onClick={() => run.mutate()}>{t("cheque.add")}</Button></Footer>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("cheque.no")}>{(id) => <Input id={id} inputMode="numeric" value={no} onChange={(e) => setNo(e.target.value)} />}</Field>
        <Field label={t("cheque.bank")} optional={t("app.optional")}>{(id) => <Input id={id} value={bank} onChange={(e) => setBank(e.target.value)} />}</Field>
        <Field label={t("charge.amount")}>{(id) => <MoneyInput id={id} value={amount} onChange={setAmount} />}</Field>
        <Field label={t("cheque.date")}>{(id) => <DateInput id={id} value={date} onChange={setDate} />}</Field>
        {run.error && <p role="alert" className="field-error sm:col-span-2">{errorMessage(run.error)}</p>}
      </div>
    </Sheet>
  );
}

export function ChequesCard({ cheques, canEdit }: { cheques: Cheque[]; canEdit: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const update = useMutation({
    mutationFn: (v: { c: Cheque; status: string }) => api.post(`/cheques/${v.c.id}/status`, { status: v.status, version: v.c.version }),
    onSuccess: () => qc.invalidateQueries(),
  });
  if (!cheques.length) return null;
  return (
    <section className="card p-4">
      <h2 className="mb-1 text-lg">{t("cheque.title")}</h2>
      <ul className="divide-y divide-line">
        {cheques.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <div className="min-w-0">
              <p className="font-semibold">{c.cheque_no}{c.bank ? ` · ${c.bank}` : ""} · {money(c.amount)}</p>
              <p className="text-sm text-muted">{dmy(c.cheque_date)}</p>
            </div>
            {canEdit ? (
              <Select aria-label={t("cheque.status")} className="w-auto" value={c.status} disabled={update.isPending}
                onChange={(e) => update.mutate({ c, status: e.target.value })}>
                {(["held", "presented", "cleared", "bounced", "returned"] as const).map((s) => <option key={s} value={s}>{t(`cheque.${s}`)}</option>)}
              </Select>
            ) : <span className="font-semibold">{t(`cheque.${c.status}`)}</span>}
          </li>
        ))}
      </ul>
      {update.error && <p role="alert" className="field-error">{errorMessage(update.error)}</p>}
    </section>
  );
}

export function EditSecuritySheet({ sec, onClose }: { sec: Security; onClose: () => void }) {
  const { t } = useTranslation();
  const [s, setS] = useState({ registration_no: sec.registration_no ?? "", insurer: sec.insurer ?? "",
    insurance_policy_no: sec.insurance_policy_no ?? "", insurance_expiry: sec.insurance_expiry ?? "", notes: sec.notes ?? "" });
  const done = useDone(onClose);
  const run = useMutation({
    mutationFn: () => api.patch(`/securities/${sec.id}`, { version: sec.version, ...Object.fromEntries(Object.entries(s).map(([k, v]) => [k, v || null])) }),
    onSuccess: done,
  });
  const text = (k: keyof typeof s, label: string) => (
    <Field label={label} optional={t("app.optional")}>{(id) => <Input id={id} value={s[k]} onChange={(e) => setS({ ...s, [k]: e.target.value })} />}</Field>
  );
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={t("security.editTitle")} description={t("security.editIntro")}
      footer={<Footer onClose={onClose}><Button loading={run.isPending} onClick={() => run.mutate()}>{t("app.save")}</Button></Footer>}>
      <div className="grid gap-3 sm:grid-cols-2">
        {sec.kind === "vehicle" && text("registration_no", t("security.registrationNo"))}
        {sec.kind === "vehicle" && text("insurer", t("security.insurer"))}
        {sec.kind === "vehicle" && text("insurance_policy_no", t("security.policyNo"))}
        {sec.kind === "vehicle" && (
          <Field label={t("security.insuranceExpiry")} optional={t("app.optional")}>
            {(id) => <DateInput id={id} value={s.insurance_expiry} onChange={(v) => setS({ ...s, insurance_expiry: v })} />}
          </Field>
        )}
        <div className="sm:col-span-2">{text("notes", t("fee.note"))}</div>
        {run.error && <p role="alert" className="field-error sm:col-span-2">{errorMessage(run.error)}</p>}
      </div>
    </Sheet>
  );
}

export function ReleaseSheet({ sec, onClose }: { sec: Security; onClose: () => void }) {
  const { t } = useTranslation();
  const [to, setTo] = useState("");
  const [on, setOn] = useState(todayIST());
  const done = useDone(onClose);
  const run = useMutation({ mutationFn: () => api.post(`/securities/${sec.id}/release`, { released_to: to, released_on: on }), onSuccess: done });
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={t("release.title")} description={t("release.intro")}
      footer={<Footer onClose={onClose}><Button loading={run.isPending} disabled={to.trim().length < 2} onClick={() => run.mutate()}>{t("release.confirm")}</Button></Footer>}>
      <div className="space-y-3">
        <Field label={t("release.to")}>{(id) => <Input id={id} value={to} onChange={(e) => setTo(e.target.value)} />}</Field>
        <Field label={t("recovery.on")}>{(id) => <DateInput id={id} max={todayIST()} value={on} onChange={setOn} />}</Field>
        {run.error && <p role="alert" className="field-error">{errorMessage(run.error)}</p>}
      </div>
    </Sheet>
  );
}

/** For a closed loan: release the documents and print the no-dues certificate. */
export function ClosedLoanCard({ loan, canEdit, onRelease }: { loan: LoanDetail; canEdit: boolean; onRelease: (s: Security) => void }) {
  const { t } = useTranslation();
  if (loan.stored_status !== "closed") return null;
  return (
    <section className="card space-y-2 p-4">
      <h2 className="text-lg">{t("release.cardTitle")}</h2>
      {loan.security.map((s) => (
        <div key={s.id} className="flex flex-wrap items-center gap-2 text-sm">
          <span>{t(`security.${s.kind}`)} {s.registration_no ?? s.survey_no ?? ""}:</span>
          {s.released_on ? <b>{t("release.done", { to: s.released_to, date: dmy(s.released_on) })}</b>
            : canEdit ? <Button size="sm" variant="outline" className="h-auto whitespace-normal py-2 text-left"
              onClick={() => onRelease(s)}>{t("release.button")}</Button> : t("release.pending")}
        </div>
      ))}
      <div className="flex flex-wrap gap-2">
        {(["ta", "en"] as const).map((pl) => (
          <Button key={pl} variant="outline" className="h-auto max-w-full whitespace-normal py-2 text-left"
            onClick={() => void openFile(`/loans/${loan.id}/no-dues.pdf`, { lang: pl })}>
            <FileCheck2 className="h-5 w-5" aria-hidden />{t("release.certificate")} · {pl === "ta" ? "தமிழ்" : "EN"}
          </Button>
        ))}
      </div>
    </section>
  );
}

export function InsuranceCard() {
  const { t } = useTranslation();
  const lang = useLang();
  const q = useQuery({ queryKey: ["insurance-due"], queryFn: () => api.get<Schemas["InsuranceDue"][]>("/insurance/due") });
  if (!q.data?.length) return null;
  return (
    <section className="card p-4" aria-labelledby="insurance-title">
      <h2 id="insurance-title" className="mb-1 flex items-center gap-2 text-lg"><ShieldAlert className="h-5 w-5 text-due" aria-hidden />{t("insurance.title")}</h2>
      <ul className="divide-y divide-line">
        {q.data.slice(0, 6).map((x) => (
          <li key={x.loan_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <Link to={`/loans/${x.loan_id}`} className="min-w-0 font-semibold underline-offset-2 hover:underline">
              {displayName(lang, x.borrower.name_en, x.borrower.name_ta)} · {x.registration_no ?? x.loan_no}
            </Link>
            <span className={x.expired ? "font-semibold text-late" : "text-due"}>
              {x.expired ? t("insurance.expired", { date: dmy(x.insurance_expiry) }) : t("insurance.expires", { date: dmy(x.insurance_expiry) })}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
