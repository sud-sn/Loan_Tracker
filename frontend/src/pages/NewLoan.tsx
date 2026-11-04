import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, UserPlus } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { ApiError, api } from "@/api/client";
import type { AppSettings, Borrower, BorrowerDetail, LoanDetail, Preview, SearchResult, TermsIn } from "@/api/types";
import { DateInput } from "@/components/DateInput";
import { Documents } from "@/components/Documents";
import { MoneyInput } from "@/components/MoneyInput";
import { ScheduleList } from "@/components/ScheduleList";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/field";
import { Segmented } from "@/components/ui/segmented";
import { KeyValue } from "@/components/ui/states";
import { Switch } from "@/components/ui/switch";
import { useDebounced } from "@/hooks/useOnline";
import { errorMessage, useLang } from "@/i18n";
import { displayName, dmy, money, todayIST } from "@/lib/format";
import { cn, newKey } from "@/lib/utils";

import { BorrowerForm } from "./BorrowerForm";

type Frequency = "monthly" | "weekly" | "daily" | "single";
type FixedMode = "period" | "amount" | "split";
type Style = "flat" | "reducing";

interface Row { principal_part: string; interest_part: string }

interface TermsState {
  principal: string;
  rate: string;
  rateBasis: "month" | "year";
  frequency: Frequency;
  fixedOn: boolean;
  fixedMode: FixedMode;
  style: Style;
  method: "reducing" | "flat" | "interest_only" | "simple_days";
  termValue: string;
  termUnit: "months" | "days" | "installments";
  fixedAmount: string;
  customInterest: string;
  customPrincipal: string;
  rows: Row[] | null;
  disbursalDate: string;
  firstDueDate: string;
  disbursalMode: "cash" | "upi" | "bank" | "cheque" | "other";
  penaltyMode: "off" | "per_day" | "pct_month";
  penaltyValue: string;
  graceDays: string;
  purpose: string;
  notes: string;
}

const INITIAL: TermsState = {
  principal: "", rate: "2", rateBasis: "month", frequency: "monthly", fixedOn: false, fixedMode: "amount",
  style: "flat", method: "reducing", termValue: "12", termUnit: "months", fixedAmount: "", customInterest: "",
  customPrincipal: "", rows: null, disbursalDate: todayIST(), firstDueDate: "", disbursalMode: "cash",
  penaltyMode: "off", penaltyValue: "", graceDays: "0", purpose: "", notes: "",
};

/** Turn what the lender chose into the API's terms (PRD section 4 plus the fixed-amount toggle). */
export function toTerms(s: TermsState): TermsIn | null {
  if (!s.principal || Number(s.principal) <= 0) return null;
  const base = {
    principal: s.principal, rate: s.rate || "0", rate_basis: s.rateBasis, frequency: s.frequency,
    disbursal_date: s.disbursalDate, first_due_date: s.firstDueDate || null,
  };
  const term = { term_value: s.termValue ? Number(s.termValue) : null, term_unit: s.termUnit };
  if (s.frequency === "single") return { ...base, ...term, method: "simple_days" } as TermsIn;
  if (!s.fixedOn) return { ...base, ...term, method: s.method === "simple_days" ? "reducing" : s.method } as TermsIn;
  if (s.fixedMode === "period") return { ...base, ...term, method: s.style === "flat" ? "flat" : "reducing" } as TermsIn;
  if (s.fixedMode === "amount") {
    if (!s.fixedAmount) return null;
    return { ...base, method: "fixed_amount", fixed_installment: s.fixedAmount, fixed_style: s.style } as TermsIn;
  }
  if (s.rows) return { ...base, method: "custom", custom_rows: s.rows } as TermsIn;
  if (!s.customPrincipal) return null;
  return { ...base, method: "custom", custom_principal: s.customPrincipal,
    custom_interest: s.customInterest || null } as TermsIn;
}

export function NewLoanPage() {
  const { t } = useTranslation();
  const lang = useLang();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  // Started from a borrower's page: the borrower is already chosen, so begin at the terms.
  const [step, setStep] = useState(params.get("borrower") ? 2 : 1);
  const [borrowerId, setBorrowerId] = useState(params.get("borrower") ?? "");
  const [s, setS] = useState<TermsState>(INITIAL);
  const [ack, setAck] = useState(false);
  const [key] = useState(() => newKey("loan"));
  const [saved, setSaved] = useState<LoanDetail | null>(null);
  const set = <K extends keyof TermsState>(k: K, v: TermsState[K]) => setS((prev) => ({ ...prev, [k]: v }));

  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.get<AppSettings>("/settings") });
  const borrower = useQuery({ queryKey: ["borrower", borrowerId], enabled: !!borrowerId,
    queryFn: () => api.get<BorrowerDetail>(`/borrowers/${borrowerId}`) });
  const terms = useMemo(() => toTerms(s), [s]);
  const debouncedTerms = useDebounced(terms, 120);
  const preview = useQuery({
    queryKey: ["preview", debouncedTerms],
    queryFn: () => api.post<Preview>("/loans/preview", debouncedTerms),
    enabled: !!debouncedTerms,
    placeholderData: keepPreviousData,
    retry: false,
  });
  const save = useMutation({
    mutationFn: () => api.post<LoanDetail>("/loans", {
      borrower_id: borrowerId, terms, disbursal_mode: s.disbursalMode, purpose: s.purpose || null, notes: s.notes || null,
      penalty: { mode: s.penaltyMode, value: s.penaltyValue || "0", grace_days: Number(s.graceDays || 0) },
      acknowledge_rate_warning: ack, idempotency_key: key,
    }),
    onSuccess: (loan) => {
      setSaved(loan);
      setStep(4);
    },
  });
  const period = t(`period.${s.frequency}`);
  const p = preview.data;
  const previewError = preview.error instanceof ApiError ? errorMessage(preview.error) : "";

  const stepTitles = [t("loan.stepBorrower"), t("loan.stepTerms"), t("loan.stepReview"), t("loan.stepSave")];
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl">{t("loan.new")}</h1>
        {/* Numbers only in the bar; the current step's name is written out below, so long Tamil
            words never get cut off at phone width. */}
        <ol className="mt-3 grid grid-cols-4 gap-1" aria-label={t("loan.step", { n: step })}>
          {stepTitles.map((title, i) => (
            <li key={title} aria-current={step === i + 1 ? "step" : undefined} aria-label={title}
              className={cn("flex h-10 items-center justify-center rounded-lg text-base font-bold",
                step === i + 1 ? "bg-brand text-brand-ink" : step > i + 1 ? "bg-brand-soft text-brand" : "bg-sunken text-muted")}>
              {i + 1}
            </li>
          ))}
        </ol>
        <p className="mt-2 font-semibold text-brand">{t("loan.step", { n: step })} · {stepTitles[step - 1]}</p>
      </div>

      {step === 1 && (
        <StepBorrower borrowerId={borrowerId} onPick={(id) => { setBorrowerId(id); setStep(2); }} />
      )}

      {step >= 2 && step <= 3 && borrower.data && (
        <div className="flex items-center justify-between gap-2 rounded-xl bg-brand-soft px-3 py-2 text-brand">
          <span className="font-semibold">{displayName(lang, borrower.data.name_en, borrower.data.name_ta)} · <span className="whitespace-nowrap">{borrower.data.code}</span></span>
          <Button size="sm" variant="ghost" onClick={() => setStep(1)}>{t("loan.change")}</Button>
        </div>
      )}
      {step >= 2 && step <= 3 && borrower.data?.profile_incomplete && (
        <p className="rounded-xl bg-due-soft p-3 font-semibold text-due">{t("borrower.incomplete")}</p>
      )}

      {step === 2 && (
        <section className="space-y-4">
          <Field label={t("loan.principal")}>
            {(id, d) => <MoneyInput id={id} describedBy={d} value={s.principal} onChange={(v) => set("principal", v)} autoFocus />}
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("loan.rate")}>
              {(id) => <Input id={id} inputMode="decimal" value={s.rate} className="tabular"
                onChange={(e) => set("rate", e.target.value.replace(/[^\d.]/g, ""))} />}
            </Field>
            <Field label={t("loan.rateBasis")}>
              {(id) => (
                <Select id={id} value={s.rateBasis} onChange={(e) => set("rateBasis", e.target.value as "month" | "year")}>
                  <option value="month">{t("rateBasis.month")}</option>
                  <option value="year">{t("rateBasis.year")}</option>
                </Select>
              )}
            </Field>
          </div>
          <Segmented label={t("loan.frequency")} value={s.frequency} columns={4}
            onChange={(v) => setS((prev) => ({ ...prev, frequency: v, rows: null,
              termUnit: v === "single" || v === "daily" ? "days" : v === "weekly" ? "installments" : "months",
              termValue: v === "single" ? "90" : v === "daily" ? "100" : v === "weekly" ? "12" : prev.termValue }))}
            options={(["monthly", "weekly", "daily", "single"] as const).map((f) => ({ value: f, label: t(`frequency.${f}`) }))} />

          {s.frequency !== "single" && (
            <Switch checked={s.fixedOn} onCheckedChange={(v) => setS((prev) => ({ ...prev, fixedOn: v, rows: null }))}
              label={t("loan.fixedToggle", { period })} hint={t("loan.fixedToggleHint")} />
          )}

          {s.frequency !== "single" && s.fixedOn && (
            <div className="space-y-4 rounded-2xl border-2 border-brand/40 bg-brand-soft/40 p-4">
              <Segmented label={t("loan.fixedMode")} value={s.fixedMode} columns={3}
                onChange={(v) => setS((prev) => ({ ...prev, fixedMode: v, rows: null }))}
                options={[
                  { value: "amount", label: t("loan.fixedFromAmount"), hint: t("loan.fixedFromAmountHint") },
                  { value: "period", label: t("loan.fixedFromPeriod"), hint: t("loan.fixedFromPeriodHint") },
                  { value: "split", label: t("loan.fixedSplit"), hint: t("loan.fixedSplitHint", { period }) },
                ]} />
              {s.fixedMode === "amount" && (
                <Field label={t("loan.fixedAmount", { period })}>
                  {(id) => <MoneyInput id={id} value={s.fixedAmount} onChange={(v) => set("fixedAmount", v)} />}
                </Field>
              )}
              {s.fixedMode === "split" && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label={t("loan.customPrincipal", { period })}>
                    {(id) => <MoneyInput id={id} value={s.customPrincipal}
                      onChange={(v) => setS((prev) => ({ ...prev, customPrincipal: v, rows: null }))} />}
                  </Field>
                  <Field label={t("loan.customInterest", { period })} hint={t("loan.customInterestHint")}>
                    {(id, d) => <MoneyInput id={id} describedBy={d} value={s.customInterest}
                      onChange={(v) => setS((prev) => ({ ...prev, customInterest: v, rows: null }))} />}
                  </Field>
                </div>
              )}
              {s.fixedMode !== "split" && (
                <Segmented label={t("loan.fixedStyle")} value={s.style} onChange={(v) => set("style", v)}
                  options={[
                    { value: "flat", label: t("loan.styleFlat"), hint: t("method.flat_hint") },
                    { value: "reducing", label: t("loan.styleReducing"), hint: t("method.reducing_hint") },
                  ]} />
              )}
            </div>
          )}

          {s.frequency !== "single" && !s.fixedOn && (
            <Segmented label={t("loan.method")} value={s.method} onChange={(v) => set("method", v)}
              options={(["reducing", "flat", "interest_only"] as const).map((m) => ({ value: m, label: t(`method.${m}`),
                hint: t(`method.${m}_hint`) }))} />
          )}

          {(s.frequency === "single" || !s.fixedOn || s.fixedMode === "period") && (
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("loan.termValue")}>
                {(id) => <Input id={id} inputMode="numeric" value={s.termValue} className="tabular"
                  onChange={(e) => set("termValue", e.target.value.replace(/\D/g, ""))} />}
              </Field>
              <Field label={t("loan.term")}>
                {(id) => (
                  <Select id={id} value={s.termUnit} onChange={(e) => set("termUnit", e.target.value as TermsState["termUnit"])}>
                    {(s.frequency === "single" ? ["days", "months"] : ["months", "days", "installments"]).map((u) => (
                      <option key={u} value={u}>{t(`termUnit.${u}`)}</option>
                    ))}
                  </Select>
                )}
              </Field>
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-3">
            <Field label={t("loan.disbursalDate")} hint={t("loan.pastHint")}>
              {(id, d) => <DateInput id={id} describedBy={d} max={todayIST()} value={s.disbursalDate}
                onChange={(v) => set("disbursalDate", v)} />}
            </Field>
            {s.frequency !== "single" && (
              <Field label={t("loan.firstDueDate")} optional={t("app.optional")}>
                {(id) => <DateInput id={id} min={s.disbursalDate} value={s.firstDueDate}
                  onChange={(v) => set("firstDueDate", v)} />}
              </Field>
            )}
            <Field label={t("loan.disbursalMode")}>
              {(id) => (
                <Select id={id} value={s.disbursalMode} onChange={(e) => set("disbursalMode", e.target.value as TermsState["disbursalMode"])}>
                  {(["cash", "upi", "bank", "cheque", "other"] as const).map((m) => <option key={m} value={m}>{t(`mode.${m}`)}</option>)}
                </Select>
              )}
            </Field>
          </div>

          <details className="rounded-xl border border-line bg-surface p-3">
            <summary className="min-h-touch cursor-pointer py-2 font-semibold">{t("loan.penaltyTitle")}</summary>
            <div className="mt-2 space-y-3">
              <Segmented value={s.penaltyMode} columns={3} onChange={(v) => set("penaltyMode", v)}
                options={[{ value: "off", label: t("loan.penaltyOff") }, { value: "per_day", label: t("loan.penaltyPerDay") },
                  { value: "pct_month", label: t("loan.penaltyPct") }]} />
              {s.penaltyMode !== "off" && (
                <div className="grid grid-cols-2 gap-3">
                  <Field label={t("loan.penaltyValue")}>
                    {(id) => <Input id={id} inputMode="decimal" value={s.penaltyValue}
                      onChange={(e) => set("penaltyValue", e.target.value.replace(/[^\d.]/g, ""))} />}
                  </Field>
                  <Field label={t("loan.graceDays")}>
                    {(id) => <Input id={id} inputMode="numeric" value={s.graceDays}
                      onChange={(e) => set("graceDays", e.target.value.replace(/\D/g, ""))} />}
                  </Field>
                </div>
              )}
            </div>
          </details>
          <Field label={t("loan.purpose")} optional={t("app.optional")}>
            {(id) => <Input id={id} value={s.purpose} onChange={(e) => set("purpose", e.target.value)} />}
          </Field>

          <PreviewCard p={p} error={previewError} loading={preview.isFetching} period={period}
            fixedNote={s.fixedOn && p ? t("loan.fixedNote", { amount: money(p.installment), period }) : undefined} />
          <div className="sticky bottom-20 z-10 flex gap-2 lg:bottom-4">
            <Button variant="outline" onClick={() => setStep(1)}><ArrowLeft className="h-5 w-5" aria-hidden />{t("app.back")}</Button>
            <Button size="lg" className="flex-1" disabled={!p || !!previewError} onClick={() => setStep(3)}>
              {t("app.next")}<ArrowRight className="h-5 w-5" aria-hidden />
            </Button>
          </div>
        </section>
      )}

      {step === 3 && p && (
        <section className="space-y-4">
          <PreviewCard p={p} error={previewError} loading={preview.isFetching} period={period}
            fixedNote={s.fixedOn ? t("loan.fixedNote", { amount: money(p.installment), period }) : undefined} />
          {p.rate_above_maximum && (
            <div className="space-y-2 rounded-xl border border-late/40 bg-late-soft p-3 text-late">
              <p className="flex items-start gap-2 font-semibold"><AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
                {t("loan.rateWarning", { rate: p.monthly_rate_equivalent, max: p.max_rate_monthly })}</p>
              <label className="flex min-h-touch items-center gap-3 text-ink">
                <input type="checkbox" className="h-6 w-6" checked={ack} onChange={(e) => setAck(e.target.checked)} />
                {t("loan.rateWarningAck")}
              </label>
            </div>
          )}
          <ScheduleEditor p={p} editable={s.fixedOn && s.fixedMode === "split"} rows={s.rows} principal={s.principal}
            onRows={(rows) => set("rows", rows)} />
          {save.error && <p role="alert" className="field-error">{errorMessage(save.error)}</p>}
          <div className="sticky bottom-20 z-10 flex gap-2 lg:bottom-4">
            <Button variant="outline" onClick={() => setStep(2)}><ArrowLeft className="h-5 w-5" aria-hidden />{t("app.back")}</Button>
            <Button size="lg" variant="paid" className="flex-1" loading={save.isPending}
              disabled={(p.rate_above_maximum && !ack) || !!previewError || !terms} onClick={() => save.mutate()}>
              {t("loan.save")}
            </Button>
          </div>
        </section>
      )}

      {step === 4 && saved && (
        <section className="space-y-4">
          <div className="flex items-start gap-3 rounded-2xl bg-paid-soft p-4 text-paid">
            <CheckCircle2 className="h-8 w-8 shrink-0" aria-hidden />
            <div>
              <h2 className="text-xl">{t("loan.savedTitle")}</h2>
              <p className="text-ink">{t("loan.savedLine", { loanNo: saved.loan_no, code: saved.borrower.code,
                name: displayName(lang, saved.borrower.name_en, saved.borrower.name_ta) })}</p>
            </div>
          </div>
          <div className="card p-4"><Documents ownerType="loan" ownerId={saved.id} maxMb={settings.data?.max_upload_mb} /></div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => navigate(`/loans/${saved.id}`)}>{t("loan.openLoan")}</Button>
            <Button variant="outline" onClick={() => { setS(INITIAL); setSaved(null); setStep(1); setBorrowerId(""); }}>
              {t("loan.another")}
            </Button>
          </div>
        </section>
      )}
    </div>
  );
}

function StepBorrower({ borrowerId, onPick }: { borrowerId: string; onPick: (id: string) => void }) {
  const { t } = useTranslation();
  const lang = useLang();
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState(false);
  const debounced = useDebounced(q.trim(), 180);
  const results = useQuery({ queryKey: ["search", debounced], enabled: !!debounced && debounced.replace(/\D/g, "").length <= 10,
    queryFn: () => api.get<SearchResult[]>("/search", { q: debounced }) });
  if (adding) {
    return (
      <div className="card p-4">
        <h2 className="mb-3 text-lg">{t("borrower.newTitle")}</h2>
        <BorrowerForm inline onSaved={(b: Borrower) => onPick(b.id)} />
      </div>
    );
  }
  const unique = (results.data ?? []).filter((r, i, all) => all.findIndex((x) => x.borrower_id === r.borrower_id) === i);
  return (
    <section className="space-y-3">
      <Field label={t("loan.pickBorrower")}>
        {(id) => <Input id={id} type="search" autoFocus value={q} placeholder={t("app.searchPlaceholder")}
          onChange={(e) => setQ(e.target.value)} />}
      </Field>
      <ul className="space-y-2">
        {unique.map((r) => (
          <li key={r.borrower_id}>
            <button onClick={() => onPick(r.borrower_id)}
              className={cn("card flex min-h-touch w-full items-center justify-between gap-3 p-3 text-left hover:bg-sunken",
                borrowerId === r.borrower_id && "border-brand")}>
              <span>
                <span className="block font-semibold">{displayName(lang, r.name_en, r.name_ta)}</span>
                <span className="block text-sm text-muted">{r.code}{r.phone ? ` · ${r.phone}` : ""}</span>
              </span>
              <span className="tabular">{money(r.outstanding)}</span>
            </button>
          </li>
        ))}
      </ul>
      <Button variant="secondary" className="w-full" onClick={() => setAdding(true)}>
        <UserPlus className="h-5 w-5" aria-hidden />{t("loan.orAddNew")}
      </Button>
      <Link to="/borrowers" className="sr-only">{t("nav.borrowers")}</Link>
    </section>
  );
}

function PreviewCard({ p, error, loading, period, fixedNote }: { p?: Preview; error: string; loading: boolean;
  period: string; fixedNote?: string }) {
  const { t } = useTranslation();
  if (error) return <p role="alert" className="rounded-xl bg-late-soft p-3 font-semibold text-late">{error}</p>;
  if (!p) return null;
  return (
    <section aria-live="polite" aria-busy={loading} className={cn("card p-4 transition-opacity", loading && "opacity-70")}>
      <p className="text-sm text-muted">{t("loan.installment")} · {period}</p>
      <p className="text-3xl font-bold text-brand tabular">{money(p.installment)}</p>
      {fixedNote && <p className="font-semibold text-brand">{fixedNote}</p>}
      <dl className="mt-2">
        <KeyValue label={t("loan.installments")} value={p.installments} />
        {p.last_installment !== p.installment && <KeyValue label={t("loan.lastInstallment")} value={money(p.last_installment)} />}
        <KeyValue label={t("loan.totalInterest")} value={money(p.total_interest)} />
        <KeyValue label={t("loan.totalPayable")} value={money(p.total_payable)} strong />
        <KeyValue label={t("loan.maturity")} value={dmy(p.maturity_date)} />
      </dl>
    </section>
  );
}

function ScheduleEditor({ p, editable, rows, principal, onRows }: { p: Preview; editable: boolean; rows: Row[] | null;
  principal: string; onRows: (rows: Row[] | null) => void }) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const current: Row[] = rows ?? p.rows.map((r) => ({ principal_part: r.principal_part, interest_part: r.interest_part }));
  const sum = current.reduce((acc, r) => acc + Math.round(Number(r.principal_part || 0) * 100), 0);
  const expected = Math.round(Number(principal) * 100);
  const mismatch = editing && sum !== expected;
  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-lg">{t("loan.schedule")}</h2>
        {editable && <Button size="sm" variant="outline" onClick={() => { setEditing(!editing); if (editing) onRows(null); }}>
          {editing ? t("app.cancel") : t("loan.editRows")}</Button>}
      </div>
      {mismatch && (
        <p role="alert" className="field-error">{t("loan.rowsMismatch", { actual: money(sum / 100), expected: money(expected / 100),
          difference: money((expected - sum) / 100) })}</p>
      )}
      {!editing && <ScheduleList rows={p.rows} />}
      {editing && <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full min-w-[520px] text-sm">
          <thead className="bg-sunken text-left">
            <tr>
              <th className="px-2 py-2">{t("loan.seq")}</th>
              <th className="px-2 py-2">{t("loan.dueDate")}</th>
              <th className="px-2 py-2 text-right">{t("loan.installment")}</th>
              <th className="px-2 py-2 text-right">{t("loan.principalPart")}</th>
              <th className="px-2 py-2 text-right">{t("loan.interestPart")}</th>
              <th className="px-2 py-2 text-right">{t("loan.balance")}</th>
            </tr>
          </thead>
          <tbody>
            {p.rows.map((r, i) => (
              <tr key={r.seq} className="border-t border-line">
                <td className="px-2 py-2">{r.seq}</td>
                <td className="px-2 py-2">{dmy(r.due_date)}</td>
                <td className="px-2 py-2 text-right tabular font-semibold">{money(r.installment)}</td>
                {editing ? (
                  <>
                    <td className="px-1 py-1"><input aria-label={`${t("loan.principalPart")} ${r.seq}`} inputMode="decimal"
                      className="control min-h-[40px] text-right" value={current[i]?.principal_part ?? ""}
                      onChange={(e) => onRows(current.map((x, j) => (j === i ? { ...x, principal_part: e.target.value.replace(/[^\d.]/g, "") } : x)))} /></td>
                    <td className="px-1 py-1"><input aria-label={`${t("loan.interestPart")} ${r.seq}`} inputMode="decimal"
                      className="control min-h-[40px] text-right" value={current[i]?.interest_part ?? ""}
                      onChange={(e) => onRows(current.map((x, j) => (j === i ? { ...x, interest_part: e.target.value.replace(/[^\d.]/g, "") } : x)))} /></td>
                  </>
                ) : (
                  <>
                    <td className="px-2 py-2 text-right tabular">{money(r.principal_part)}</td>
                    <td className="px-2 py-2 text-right tabular">{money(r.interest_part)}</td>
                  </>
                )}
                <td className="px-2 py-2 text-right tabular">{money(r.closing_balance)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>}
    </section>
  );
}
