import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Printer, Share2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, openFile, shareFile } from "@/api/client";
import type { LoanDetail, Payment } from "@/api/types";
import { errorMessage, useLang } from "@/i18n";
import { displayName, dmy, money, todayIST } from "@/lib/format";
import { newKey } from "@/lib/utils";

import { DateInput } from "./DateInput";
import { MoneyInput } from "./MoneyInput";
import { Button } from "./ui/button";
import { Sheet } from "./ui/dialog";
import { Field, Input, Select } from "./ui/field";
import { KeyValue } from "./ui/states";

const MODES = ["cash", "upi", "bank", "cheque", "other"] as const;

/** Record a payment in as few taps as possible, then show exactly how it was split (PRD section 5). */
export function RecordPaymentSheet({ loanId, initialAmount, onClose }: { loanId: string; initialAmount?: string;
  onClose: () => void }) {
  const { t } = useTranslation();
  const lang = useLang();
  const qc = useQueryClient();
  const loan = useQuery({ queryKey: ["loan", loanId], queryFn: () => api.get<LoanDetail>(`/loans/${loanId}`) });
  const dueNow = useMemo(() => {
    const s = loan.data?.summary;
    if (!s) return "";
    const n = Number(s.overdue_amount) + Number(s.due_today_amount);
    return n > 0 ? n.toFixed(2) : s.next_due_amount;
  }, [loan.data]);
  const [amount, setAmount] = useState(initialAmount ?? "");
  const [date, setDate] = useState(todayIST());
  const [mode, setMode] = useState<(typeof MODES)[number]>("cash");
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  // One idempotency key per form: a double tap or a retry can never save twice (PRD section 5).
  const [key] = useState(() => newKey("pay"));
  const [result, setResult] = useState<Payment | null>(null);
  const shownAmount = amount || (initialAmount ? initialAmount : dueNow);

  const save = useMutation({
    mutationFn: () => api.post<Payment>(`/loans/${loanId}/payments`, {
      amount: shownAmount, paid_on: date, mode, reference: reference || null, note: note || null, idempotency_key: key,
    }),
    onSuccess: (p) => {
      setResult(p);
      void qc.invalidateQueries();
    },
  });

  const name = loan.data ? displayName(lang, loan.data.borrower.name_en, loan.data.borrower.name_ta) : "";
  if (result) {
    return (
      <Sheet open onOpenChange={(o) => !o && onClose()} title={t("payment.savedTitle")}
        description={`${t("payment.receiptNo", { no: result.receipt_no })} · ${name}`}
        footer={<>
          <Button variant="outline" onClick={() => void shareFile(`/payments/${result.id}/receipt.pdf`)}>
            <Share2 className="h-4 w-4" aria-hidden />{t("payment.shareReceipt")}
          </Button>
          <Button variant="outline" onClick={() => void openFile(`/payments/${result.id}/receipt.pdf`)}>
            <Printer className="h-4 w-4" aria-hidden />{t("payment.receipt")}
          </Button>
          <Button onClick={onClose}>{t("app.done")}</Button>
        </>}>
        <div className="mb-4 flex items-center gap-3 rounded-xl bg-paid-soft p-4 text-paid">
          <CheckCircle2 className="h-8 w-8 shrink-0" aria-hidden />
          <span className="text-2xl font-bold tabular">{money(result.amount)}</span>
        </div>
        <h3 className="mb-1 font-semibold">{t("payment.split")}</h3>
        <dl>
          {Number(result.penalty_total) > 0 && <KeyValue label={t("payment.penalty")} value={money(result.penalty_total)} />}
          <KeyValue label={t("payment.interest")} value={money(result.interest_total)} />
          <KeyValue label={t("payment.principal")} value={money(result.principal_total)} />
          <KeyValue label={t("payment.balanceAfter")} value={money(result.balance_after)} strong />
        </dl>
        <ul className="mt-3 space-y-1 text-sm text-muted">
          {result.allocations.map((a) => (
            <li key={a.seq}>
              #{a.seq} · {dmy(a.due_date)} — {t("payment.interest")} {money(a.interest_part)}, {t("payment.principal")} {money(a.principal_part)}
              {Number(a.penalty_part) > 0 && `, ${t("payment.penalty")} ${money(a.penalty_part)}`}
            </li>
          ))}
        </ul>
      </Sheet>
    );
  }

  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={t("payment.title")}
      description={loan.data ? `${name} · ${loan.data.borrower.code} · ${loan.data.loan_no}` : t("app.loading")}
      footer={<>
        <Button variant="outline" onClick={onClose}>{t("app.cancel")}</Button>
        <Button variant="paid" size="lg" loading={save.isPending} disabled={!shownAmount || Number(shownAmount) <= 0}
          onClick={() => save.mutate()}>{t("payment.save")}</Button>
      </>}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        {dueNow && <p className="rounded-xl bg-due-soft px-3 py-2 font-semibold text-due">{t("payment.dueNow", { amount: money(dueNow) })}</p>}
        <Field label={t("payment.amount")} error={save.error ? errorMessage(save.error) : undefined}>
          {(id, d) => <MoneyInput id={id} describedBy={d} value={shownAmount} onChange={setAmount} autoFocus />}
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("payment.date")}>
            {(id) => <DateInput id={id} value={date} max={todayIST()} onChange={setDate} />}
          </Field>
          <Field label={t("payment.mode")}>
            {(id) => (
              <Select id={id} value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}>
                {MODES.map((m) => <option key={m} value={m}>{t(`mode.${m}`)}</option>)}
              </Select>
            )}
          </Field>
        </div>
        {mode !== "cash" && (
          <Field label={t("payment.reference")} optional={t("app.optional")}>
            {(id) => <Input id={id} value={reference} onChange={(e) => setReference(e.target.value)} />}
          </Field>
        )}
        <Field label={t("payment.note")} optional={t("app.optional")}>
          {(id) => <Input id={id} value={note} onChange={(e) => setNote(e.target.value)} />}
        </Field>
      </form>
    </Sheet>
  );
}
