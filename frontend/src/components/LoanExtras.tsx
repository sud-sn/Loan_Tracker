import { AlertTriangle, Plus, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { AppSettings, ChargeIn, Preview, SecurityIn } from "@/api/types";
import { DateInput } from "@/components/DateInput";
import { MoneyInput } from "@/components/MoneyInput";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/field";
import { Segmented } from "@/components/ui/segmented";
import { KeyValue } from "@/components/ui/states";
import { money } from "@/lib/format";
import { cn } from "@/lib/utils";

// Vehicle and land loans: what the loan is given against, charges collected when it is given, and
// the options for the installment (rounding, advance EMIs, an odd first period).

export type SecurityKind = "none" | "vehicle" | "land";
export type VehicleType = "two_wheeler" | "three_wheeler" | "car" | "commercial" | "tractor" | "other";
export type Original = NonNullable<SecurityIn["originals_held"]>[number];

export interface SecurityState {
  kind: SecurityKind;
  vehicleType: VehicleType;
  condition: "new" | "used";
  registrationNo: string;
  makeModel: string;
  year: string;
  chassisNo: string;
  engineNo: string;
  price: string; // on-road price (new) or valuation (used)
  downPayment: string;
  insurer: string;
  policyNo: string;
  insuranceExpiry: string;
  lienNoted: boolean;
  surveyNo: string;
  pattaNo: string;
  extent: string;
  village: string;
  taluk: string;
  district: string;
  documentNo: string;
  sro: string;
  guidelineValue: string;
  marketValue: string;
  ecChecked: boolean;
  ecDate: string;
  originals: Original[];
}

export const EMPTY_SECURITY: SecurityState = {
  kind: "none", vehicleType: "two_wheeler", condition: "new", registrationNo: "", makeModel: "", year: "",
  chassisNo: "", engineNo: "", price: "", downPayment: "", insurer: "", policyNo: "", insuranceExpiry: "",
  lienNoted: false, surveyNo: "", pattaNo: "", extent: "", village: "", taluk: "", district: "", documentNo: "",
  sro: "", guidelineValue: "", marketValue: "", ecChecked: false, ecDate: "", originals: [],
};

const VEHICLE_ORIGINALS: Original[] = ["rc_book", "duplicate_key", "insurance_copy", "blank_cheques", "promissory_note", "other"];
const LAND_ORIGINALS: Original[] = ["sale_deed", "patta", "ec", "parent_documents", "tax_receipt", "promissory_note",
  "blank_cheques", "other"];

const orNull = (v: string) => (v.trim() ? v.trim() : null);

/** Loan amount suggested by a vehicle: price less down payment. */
export function suggestedAmount(sec: SecurityState): string {
  if (sec.kind !== "vehicle" || !sec.price) return "";
  const amount = Number(sec.price) - Number(sec.downPayment || 0);
  return amount > 0 ? String(Math.round(amount * 100) / 100) : "";
}

export function securityPayload(sec: SecurityState): SecurityIn[] {
  if (sec.kind === "vehicle") {
    return [{
      kind: "vehicle", vehicle_type: sec.vehicleType, vehicle_condition: sec.condition,
      registration_no: orNull(sec.registrationNo), make_model: orNull(sec.makeModel), year: sec.year ? Number(sec.year) : null,
      chassis_no: orNull(sec.chassisNo), engine_no: orNull(sec.engineNo),
      on_road_price: sec.condition === "new" ? orNull(sec.price) : null,
      value: sec.condition === "used" ? orNull(sec.price) : null,
      down_payment: orNull(sec.downPayment), insurer: orNull(sec.insurer), insurance_policy_no: orNull(sec.policyNo),
      insurance_expiry: orNull(sec.insuranceExpiry), lien_noted_on_rc: sec.lienNoted,
      originals_held: sec.originals.filter((o) => VEHICLE_ORIGINALS.includes(o)),
    } as SecurityIn];
  }
  if (sec.kind === "land") {
    return [{
      kind: "land", survey_no: orNull(sec.surveyNo), patta_no: orNull(sec.pattaNo), extent: orNull(sec.extent),
      village: orNull(sec.village), taluk: orNull(sec.taluk), district: orNull(sec.district),
      document_no: orNull(sec.documentNo), sub_registrar_office: orNull(sec.sro),
      guideline_value: orNull(sec.guidelineValue), market_value: orNull(sec.marketValue),
      ec_checked: sec.ecChecked, ec_date: orNull(sec.ecDate),
      originals_held: sec.originals.filter((o) => LAND_ORIGINALS.includes(o)),
    } as SecurityIn];
  }
  return [];
}

export function SecurityStep({ sec, onChange }: { sec: SecurityState; onChange: (next: SecurityState) => void }) {
  const { t } = useTranslation();
  const set = <K extends keyof SecurityState>(k: K, v: SecurityState[K]) => onChange({ ...sec, [k]: v });
  const text = (k: keyof SecurityState, label: string, opts: { upper?: boolean; numeric?: boolean } = {}) => (
    <Field label={label} optional={t("app.optional")}>
      {(id) => <Input id={id} value={sec[k] as string} inputMode={opts.numeric ? "numeric" : undefined}
        className={cn(opts.upper && "uppercase")}
        onChange={(e) => set(k, (opts.numeric ? e.target.value.replace(/\D/g, "") : e.target.value) as never)} />}
    </Field>
  );
  const originals = sec.kind === "vehicle" ? VEHICLE_ORIGINALS : LAND_ORIGINALS;
  const suggested = suggestedAmount(sec);
  return (
    <section className="space-y-4">
      <Segmented label={t("security.question")} value={sec.kind} columns={3} onChange={(v) => set("kind", v)}
        options={[
          { value: "none", label: t("security.none"), hint: t("security.noneHint") },
          { value: "vehicle", label: t("security.vehicle"), hint: t("security.vehicleHint") },
          { value: "land", label: t("security.land"), hint: t("security.landHint") },
        ]} />

      {sec.kind === "vehicle" && (
        <div className="card space-y-4 p-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <Field label={t("security.vehicleType")}>
              {(id) => (
                <Select id={id} value={sec.vehicleType} onChange={(e) => set("vehicleType", e.target.value as VehicleType)}>
                  {(["two_wheeler", "three_wheeler", "car", "commercial", "tractor", "other"] as const).map((v) => (
                    <option key={v} value={v}>{t(`vehicleType.${v}`)}</option>
                  ))}
                </Select>
              )}
            </Field>
            <Segmented label={t("security.condition")} value={sec.condition} onChange={(v) => set("condition", v)}
              options={[{ value: "new", label: t("security.new") }, { value: "used", label: t("security.used") }]} />
            {text("registrationNo", t("security.registrationNo"), { upper: true })}
            {text("makeModel", t("security.makeModel"))}
            {text("year", t("security.year"), { numeric: true })}
            {text("chassisNo", t("security.chassisNo"), { upper: true })}
            {text("engineNo", t("security.engineNo"), { upper: true })}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={sec.condition === "new" ? t("security.onRoadPrice") : t("security.valuation")}>
              {(id) => <MoneyInput id={id} value={sec.price} onChange={(v) => set("price", v)} />}
            </Field>
            <Field label={t("security.downPayment")} optional={t("app.optional")}>
              {(id) => <MoneyInput id={id} value={sec.downPayment} onChange={(v) => set("downPayment", v)} />}
            </Field>
          </div>
          {suggested && (
            <p className="rounded-xl bg-brand-soft px-3 py-2 font-semibold text-brand">
              {t("security.suggested", { price: money(sec.price), down: money(sec.downPayment || "0"), amount: money(suggested) })}
            </p>
          )}
          <div className="grid gap-3 sm:grid-cols-3">
            {text("insurer", t("security.insurer"))}
            {text("policyNo", t("security.policyNo"))}
            <Field label={t("security.insuranceExpiry")} optional={t("app.optional")}>
              {(id) => <DateInput id={id} value={sec.insuranceExpiry} onChange={(v) => set("insuranceExpiry", v)} />}
            </Field>
          </div>
          <Check checked={sec.lienNoted} onChange={(v) => set("lienNoted", v)} label={t("security.lienNoted")} />
        </div>
      )}

      {sec.kind === "land" && (
        <div className="card space-y-4 p-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {text("surveyNo", t("security.surveyNo"))}
            {text("pattaNo", t("security.pattaNo"))}
            {text("extent", t("security.extent"))}
            {text("village", t("security.village"))}
            {text("taluk", t("security.taluk"))}
            {text("district", t("security.district"))}
            {text("documentNo", t("security.documentNo"))}
            {text("sro", t("security.sro"))}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("security.marketValue")} hint={t("security.marketValueHint")}>
              {(id, d) => <MoneyInput id={id} describedBy={d} value={sec.marketValue} onChange={(v) => set("marketValue", v)} />}
            </Field>
            <Field label={t("security.guidelineValue")} optional={t("app.optional")}>
              {(id) => <MoneyInput id={id} value={sec.guidelineValue} onChange={(v) => set("guidelineValue", v)} />}
            </Field>
          </div>
          <div className="grid items-end gap-3 sm:grid-cols-2">
            <Check checked={sec.ecChecked} onChange={(v) => set("ecChecked", v)} label={t("security.ecChecked")} />
            {sec.ecChecked && (
              <Field label={t("security.ecDate")} optional={t("app.optional")}>
                {(id) => <DateInput id={id} value={sec.ecDate} onChange={(v) => set("ecDate", v)} />}
              </Field>
            )}
          </div>
        </div>
      )}

      {sec.kind !== "none" && (
        <section role="group" aria-labelledby="originals-title" className="card p-4">
          <h2 id="originals-title" className="text-lg">{t("security.originals")}</h2>
          <p className="field-hint mb-2">{t("security.originalsHint")}</p>
          <div className="grid gap-x-4 sm:grid-cols-2 xl:grid-cols-3">
            {originals.map((o) => (
              <Check key={o} checked={sec.originals.includes(o)} label={t(`original.${o}`)}
                onChange={(v) => set("originals", v ? [...sec.originals, o] : sec.originals.filter((x) => x !== o))} />
            ))}
          </div>
        </section>
      )}
    </section>
  );
}

function Check({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex min-h-touch cursor-pointer items-center gap-3">
      <input type="checkbox" className="h-5 w-5 shrink-0 accent-[rgb(var(--brand))]" checked={checked}
        onChange={(e) => onChange(e.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

// ------------------------------------------------------------------- charges

export type ChargeKind = "processing_fee" | "document_charges" | "rto_stamp" | "insurance" | "other";
export interface ChargeRow { kind: ChargeKind; label: string; amount: string; treatment: "deducted" | "added"; auto?: boolean }

/** Charges the form starts with, from the owner's settings. The processing fee follows the loan amount
 * (a % of it) until the owner types an amount. */
export function defaultCharges(settings?: AppSettings): ChargeRow[] {
  const rows: ChargeRow[] = [];
  if (settings && Number(settings.processing_fee_percent) > 0) {
    rows.push({ kind: "processing_fee", label: "", amount: "", treatment: "deducted", auto: true });
  }
  if (settings && Number(settings.document_charges_default) > 0) {
    rows.push({ kind: "document_charges", label: "", amount: settings.document_charges_default, treatment: "deducted" });
  }
  return rows;
}

function feeFor(principal: string, percent: string | undefined): string {
  const fee = Math.round(Number(principal || 0) * Number(percent || 0)) / 100;
  return fee > 0 ? fee.toFixed(2) : "";
}

export function chargeAmount(row: ChargeRow, principal: string, settings?: AppSettings): string {
  return row.auto ? feeFor(principal, settings?.processing_fee_percent) : row.amount;
}

export function chargesPayload(rows: ChargeRow[], principal: string, settings?: AppSettings): ChargeIn[] {
  return rows
    .map((r) => ({ kind: r.kind, label: r.kind === "other" ? orNull(r.label) : null, amount: chargeAmount(r, principal, settings),
      treatment: r.treatment }))
    .filter((c) => Number(c.amount) > 0 && (c.kind !== "other" || c.label)) as ChargeIn[];
}

export function ChargesCard({ rows, onChange, principal, settings }:
  { rows: ChargeRow[]; onChange: (rows: ChargeRow[]) => void; principal: string; settings?: AppSettings }) {
  const { t } = useTranslation();
  const update = (i: number, patch: Partial<ChargeRow>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <section role="group" aria-labelledby="charges-title" className="card space-y-3 p-4">
      <div>
        <h2 id="charges-title" className="text-lg">{t("charge.title")}</h2>
        <p className="field-hint">{t("charge.hint")}</p>
      </div>
      {rows.map((r, i) => (
        <div key={i} className="grid gap-2 rounded-xl border border-line p-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-start">
          <Field label={t("charge.kind")}>
            {(id) => (
              <Select id={id} value={r.kind} onChange={(e) => update(i, { kind: e.target.value as ChargeKind, auto: false })}>
                {(["processing_fee", "document_charges", "rto_stamp", "insurance", "other"] as const).map((k) => (
                  <option key={k} value={k}>{t(`charge.${k}`)}</option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("charge.amount")} hint={r.auto ? t("charge.autoHint", { percent: settings?.processing_fee_percent }) : undefined}>
            {(id, d) => <MoneyInput id={id} describedBy={d} value={chargeAmount(r, principal, settings)}
              onChange={(v) => update(i, { amount: v, auto: false })} />}
          </Field>
          <Button variant="ghost" size="icon" className="justify-self-end sm:mt-7" aria-label={t("charge.remove")}
            onClick={() => onChange(rows.filter((_, j) => j !== i))}>
            <X className="h-5 w-5" aria-hidden />
          </Button>
          {r.kind === "other" && (
            <Field label={t("charge.label")} className="sm:col-span-3">
              {(id) => <Input id={id} value={r.label} onChange={(e) => update(i, { label: e.target.value })} />}
            </Field>
          )}
          <div className="sm:col-span-3">
            <Segmented value={r.treatment} onChange={(v) => update(i, { treatment: v })}
              options={[{ value: "deducted", label: t("charge.deducted"), hint: t("charge.deductedHint") },
                { value: "added", label: t("charge.added"), hint: t("charge.addedHint") }]} />
          </div>
        </div>
      ))}
      <Button variant="outline" onClick={() => onChange([...rows, { kind: "processing_fee", label: "", amount: "", treatment: "deducted" }])}>
        <Plus className="h-5 w-5" aria-hidden />{t("charge.add")}
      </Button>
    </section>
  );
}

// ------------------------------------------------------------------- options

export interface OptionsState { rounding: string; advance: string; brokenPeriod: "none" | "first_installment" | "upfront" }

export function LoanOptions({ o, onChange, amortizing, oddFirst }:
  { o: OptionsState; onChange: (o: OptionsState) => void; amortizing: boolean; oddFirst: boolean }) {
  const { t } = useTranslation();
  const summary = [
    amortizing ? (Number(o.rounding) >= 1 ? t("options.roundTo", { step: o.rounding }) : t("options.noRounding")) : null,
    amortizing && Number(o.advance) > 0 ? t("options.advanceCount", { count: Number(o.advance) }) : null,
    oddFirst ? t(`options.odd_${o.brokenPeriod}`) : null,
  ].filter(Boolean).join(" · ");
  return (
    <details className="rounded-xl border border-line bg-surface p-3">
      <summary className="min-h-touch cursor-pointer py-2 font-semibold">
        {t("options.title")}{summary && <span className="block text-sm font-normal text-muted">{summary}</span>}
      </summary>
      <div className="mt-2 grid gap-3 sm:grid-cols-2">
        {amortizing && (
          <Field label={t("options.rounding")} hint={t("options.roundingHint")}>
            {(id, d) => (
              <Select id={id} aria-describedby={d} value={o.rounding} onChange={(e) => onChange({ ...o, rounding: e.target.value })}>
                {["0.01", "1", "5", "10", "50", "100"].map((v) => (
                  <option key={v} value={v}>{v === "0.01" ? t("options.noRounding") : t("options.roundTo", { step: v })}</option>
                ))}
              </Select>
            )}
          </Field>
        )}
        {amortizing && (
          <Field label={t("options.advance")} hint={t("options.advanceHint")}>
            {(id, d) => (
              <Select id={id} aria-describedby={d} value={o.advance} onChange={(e) => onChange({ ...o, advance: e.target.value })}>
                {["0", "1", "2", "3"].map((v) => <option key={v} value={v}>{v}</option>)}
              </Select>
            )}
          </Field>
        )}
        <Field label={t("options.oddFirst")} hint={t("options.oddFirstHint")} className="sm:col-span-2">
          {(id, d) => (
            <Select id={id} aria-describedby={d} value={o.brokenPeriod}
              onChange={(e) => onChange({ ...o, brokenPeriod: e.target.value as OptionsState["brokenPeriod"] })}>
              {(["first_installment", "upfront", "none"] as const).map((v) => <option key={v} value={v}>{t(`options.odd_${v}`)}</option>)}
            </Select>
          )}
        </Field>
      </div>
    </details>
  );
}

// ------------------------------------------------------------------- live result lines

export function PreviewExtras({ p }: { p: Preview }) {
  const { t } = useTranslation();
  const bpi = Number(p.broken_period_interest);
  const handedDiffers = p.amount_handed_over !== p.loan_amount || Number(p.topup_closing) > 0;
  return (
    <dl className="mt-1">
      {p.unrounded_installment && <KeyValue label={t("result.roundedFrom")} value={money(p.unrounded_installment)} />}
      {bpi !== 0 && (
        <KeyValue label={t("result.firstInstallment")}
          value={<>{money(p.first_installment)}<span className="block text-xs text-muted">
            {t(bpi > 0 ? "result.extraDays" : "result.fewerDays", { count: Math.abs(p.broken_period_days), amount: money(Math.abs(bpi)) })}
          </span></>} />
      )}
      {p.advance_installments > 0 && (
        <KeyValue label={t("result.advance", { count: p.advance_installments })} value={money(p.advance_amount)} />
      )}
      {Number(p.topup_closing) > 0 && <KeyValue label={t("topup.closing")} value={money(p.topup_closing)} />}
      {Number(p.charges_added) > 0 && <KeyValue label={t("result.chargesAdded")} value={money(p.charges_added)} />}
      {Number(p.charges_deducted) > 0 && <KeyValue label={t("result.chargesDeducted")} value={money(p.charges_deducted)} />}
      {handedDiffers && <KeyValue label={t("result.handedOver")} value={money(p.amount_handed_over)} strong />}
      {p.true_cost_monthly && (
        <KeyValue label={t("result.trueCost")}
          value={t("result.trueCostValue", { monthly: p.true_cost_monthly, yearly: p.true_cost_yearly })} />
      )}
      {p.ltv_percent && (
        <KeyValue label={t("result.ltv")}
          value={<span className={cn(p.ltv_above_maximum && "font-semibold text-late")}>
            {t("result.ltvValue", { ltv: p.ltv_percent, max: p.ltv_maximum })}</span>} />
      )}
    </dl>
  );
}

export function LtvWarning({ p, ack, onAck }: { p: Preview; ack: boolean; onAck: (v: boolean) => void }) {
  const { t } = useTranslation();
  if (!p.ltv_above_maximum) return null;
  return (
    <div className="space-y-2 rounded-xl border border-late/40 bg-late-soft p-3 text-late">
      <p className="flex items-start gap-2 font-semibold"><AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
        {t("result.ltvWarning", { ltv: p.ltv_percent, max: p.ltv_maximum, value: money(p.security_value ?? "0") })}</p>
      <label className="flex min-h-touch items-center gap-3 text-ink">
        <input type="checkbox" className="h-6 w-6" checked={ack} onChange={(e) => onAck(e.target.checked)} />
        {t("result.ltvAck")}
      </label>
    </div>
  );
}

// ------------------------------------------------------------------- loan page

type LoanForCard = {
  principal: string; amount_handed_over: string; charges: { kind: string; label: string | null; amount: string; treatment: string }[];
  advance_installments: number; broken_period_days: number; broken_period_interest: string; emi_rounding: string;
  true_cost_monthly: string | null; ltv_percent: string | null;
};

/** Extra lines for the loan summary: charges, amount handed over, options, true cost, loan-to-value. */
export function LoanSummaryExtras({ l }: { l: LoanForCard }) {
  const { t } = useTranslation();
  const bpi = Number(l.broken_period_interest);
  return (
    <>
      {l.charges.map((c, i) => (
        <KeyValue key={i} label={c.kind === "other" ? c.label : t(`charge.${c.kind}`)}
          value={<>{money(c.amount)}<span className="block text-xs text-muted">{t(`charge.${c.treatment}`)}</span></>} />
      ))}
      {l.amount_handed_over !== l.principal && <KeyValue label={t("result.handedOver")} value={money(l.amount_handed_over)} strong />}
      {l.advance_installments > 0 && <KeyValue label={t("options.advance")} value={l.advance_installments} />}
      {Number(l.emi_rounding) >= 1 && <KeyValue label={t("options.rounding")} value={t("options.roundTo", { step: Number(l.emi_rounding) })} />}
      {bpi !== 0 && (
        <KeyValue label={t("result.firstInstallment")}
          value={t(bpi > 0 ? "result.extraDays" : "result.fewerDays", { count: Math.abs(l.broken_period_days), amount: money(Math.abs(bpi)) })} />
      )}
      {l.true_cost_monthly && (
        <KeyValue label={t("result.trueCost")}
          value={t("result.trueCostValue", { monthly: l.true_cost_monthly, yearly: (Number(l.true_cost_monthly) * 12).toFixed(2) })} />
      )}
      {l.ltv_percent && <KeyValue label={t("result.ltv")} value={`${l.ltv_percent}%`} />}
    </>
  );
}

/** What the loan is given against, and the originals the lender keeps. */
export function SecurityCard({ security }: { security: SecurityIn[] }) {
  const { t } = useTranslation();
  if (!security.length) return null;
  return (
    <>
      {security.map((s, i) => {
        const rows: [string, string | null | undefined][] = s.kind === "vehicle" ? [
          [t("security.registrationNo"), s.registration_no],
          [t("security.vehicleType"), s.vehicle_type ? `${t(`vehicleType.${s.vehicle_type}`)}${s.vehicle_condition ? ` · ${t(`security.${s.vehicle_condition}`)}` : ""}` : null],
          [t("security.makeModel"), s.make_model ? `${s.make_model}${s.year ? ` (${s.year})` : ""}` : null],
          [t("security.chassisNo"), s.chassis_no], [t("security.engineNo"), s.engine_no],
          [s.vehicle_condition === "used" ? t("security.valuation") : t("security.onRoadPrice"), s.value ? money(s.value) : s.on_road_price ? money(s.on_road_price) : null],
          [t("security.downPayment"), s.down_payment ? money(s.down_payment) : null],
          [t("security.insuranceExpiry"), s.insurance_expiry ? `${s.insurer ?? ""} ${s.insurance_policy_no ?? ""} · ${s.insurance_expiry.split("-").reverse().join("/")}`.trim() : null],
          [t("security.lienNoted"), s.lien_noted_on_rc ? t("app.yes") : t("app.no")],
        ] : [
          [t("security.surveyNo"), s.survey_no], [t("security.pattaNo"), s.patta_no], [t("security.extent"), s.extent],
          [t("security.place"), [s.village, s.taluk, s.district].filter(Boolean).join(", ") || null],
          [t("security.documentNo"), [s.document_no, s.sub_registrar_office].filter(Boolean).join(" · ") || null],
          [t("security.marketValue"), s.market_value ? money(s.market_value) : null],
          [t("security.guidelineValue"), s.guideline_value ? money(s.guideline_value) : null],
          [t("security.ecChecked"), s.ec_checked ? `${t("app.yes")}${s.ec_date ? ` · ${s.ec_date.split("-").reverse().join("/")}` : ""}` : t("app.no")],
        ];
        return (
          <section key={i} className="card p-4">
            <h2 className="mb-1 text-lg">{t("security.title")} · {t(`security.${s.kind}`)}</h2>
            <dl>{rows.filter(([, v]) => v).map(([k, v]) => <KeyValue key={k} label={k} value={v} />)}</dl>
            {!!s.originals_held?.length && (
              <p className="mt-2 text-sm"><span className="font-semibold">{t("security.originals")}: </span>
                {s.originals_held.map((o) => t(`original.${o}`)).join(", ")}</p>
            )}
          </section>
        );
      })}
    </>
  );
}
