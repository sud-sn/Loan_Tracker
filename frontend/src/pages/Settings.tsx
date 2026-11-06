import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, openFile } from "@/api/client";
import type { AppSettings, Category, User } from "@/api/types";
import { LanguageSwitch } from "@/components/LanguageSwitch";
import { MoneyInput } from "@/components/MoneyInput";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/field";
import { Card } from "@/components/ui/states";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/toast";
import { useAuth } from "@/hooks/useAuth";
import { errorMessage, useLang } from "@/i18n";
import { dmy } from "@/lib/format";

export function SettingsPage() {
  const { t } = useTranslation();
  const { me, isOwner, refetch } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.get<AppSettings>("/settings") });
  const [form, setForm] = useState<AppSettings | null>(null);
  useEffect(() => { if (settings.data) setForm(settings.data); }, [settings.data]);
  const save = useMutation({
    mutationFn: (data: Partial<AppSettings>) => api.put<AppSettings>("/settings", { ...data, version: form?.version }),
    onSuccess: (data) => {
      qc.setQueryData(["settings"], data);
      setForm(data);
      toast({ text: t("app.saved") });
    },
    onError: (err) => toast({ text: errorMessage(err), tone: "error" }),
  });
  const set = <K extends keyof AppSettings>(k: K, v: AppSettings[K]) => setForm((f) => (f ? { ...f, [k]: v } : f));
  // The save bar shows only when something was changed, so it never hides other buttons needlessly.
  const dirty = !!form && !!settings.data && JSON.stringify(form) !== JSON.stringify(settings.data);
  const num = (k: keyof AppSettings, label: string) => (
    <Field label={label}>
      {(id) => <Input id={id} inputMode="numeric" value={String(form?.[k] ?? "")}
        onChange={(e) => set(k, Number(e.target.value.replace(/\D/g, "")) as never)} />}
    </Field>
  );
  const theme = (() => { try { return localStorage.getItem("lt-theme") ?? "light"; } catch { return "light"; } })();
  const [currentTheme, setTheme] = useState(theme);
  const applyTheme = (v: string) => {
    setTheme(v);
    document.documentElement.dataset.theme = v;
    try { localStorage.setItem("lt-theme", v); } catch { /* ignore */ }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl xl:text-3xl">{t("settings.title")}</h1>
      {/* Cards flow in columns that follow the page width (also when the menu is folded): 1, then 2 from 60 rem, 3 from 110 rem. */}
      <div className="space-y-4 @[60rem]/main:block @[60rem]/main:columns-2 @[60rem]/main:gap-4 @[60rem]/main:space-y-0 @[60rem]/main:[&>*]:mb-4 @[60rem]/main:[&>*]:break-inside-avoid @[110rem]/main:columns-3">
      <Card>
        <h2 className="mb-3 text-lg">{t("settings.account")}</h2>
        <p className="mb-3">{me?.user.name} · {me?.user.phone}</p>
        <div className="flex flex-wrap items-center gap-4">
          <div><p className="field-label">{t("app.language")}</p><LanguageSwitch /></div>
          <div>
            <p className="field-label">{t("settings.theme")}</p>
            <div className="flex gap-2">
              {["light", "dark"].map((v) => (
                <Button key={v} size="sm" variant={currentTheme === v ? "secondary" : "outline"} onClick={() => applyTheme(v)}>
                  {t(`settings.${v}`)}
                </Button>
              ))}
            </div>
          </div>
        </div>
      </Card>
      <PasswordCard />
      {isOwner && <TwoFactorCard enabled={!!me?.user.totp_enabled} onChange={refetch} />}
      {isOwner && form && (
        <>
          <Card>
            <h2 className="mb-3 text-lg">{t("settings.cash")}</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={t("settings.startDate")}>
                {(id) => <Input id={id} type="date" value={form.balance_start_date ?? ""} onChange={(e) => set("balance_start_date", e.target.value || null)} />}
              </Field>
              <Field label={t("settings.openingBalance")}>
                {(id) => <MoneyInput id={id} value={form.opening_balance} onChange={(v) => set("opening_balance", v || "0")} />}
              </Field>
            </div>
          </Card>
          <Card>
            <h2 className="mb-3 text-lg">{t("settings.thresholds")}</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {num("due_soon_days", t("settings.dueSoon"))}
              {num("due_window_days", t("settings.dueWindow"))}
              {num("long_unpaid_days", t("settings.longUnpaid"))}
              <Field label={t("settings.summaryTime")}>
                {(id) => <Input id={id} type="time" value={(form.daily_summary_time ?? "").slice(0, 5)} onChange={(e) => set("daily_summary_time", e.target.value || null)} />}
              </Field>
              <Field label={t("settings.languageDefault")}>
                {(id) => (
                  <Select id={id} value={form.default_language} onChange={(e) => set("default_language", e.target.value as "en" | "ta")}>
                    <option value="ta">தமிழ்</option><option value="en">English</option>
                  </Select>
                )}
              </Field>
            </div>
          </Card>
          <Card>
            <h2 className="mb-3 text-lg">{t("settings.lender")}</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={t("settings.lenderName")}>{(id) => <Input id={id} value={form.lender_name ?? ""} onChange={(e) => set("lender_name", e.target.value || null)} />}</Field>
              <Field label={t("settings.lenderAddress")}>{(id) => <Input id={id} value={form.lender_address ?? ""} onChange={(e) => set("lender_address", e.target.value || null)} />}</Field>
              <Field label={t("settings.licence")} optional={t("app.optional")}>{(id) => <Input id={id} value={form.licence_no ?? ""} onChange={(e) => set("licence_no", e.target.value || null)} />}</Field>
              <Field label={t("settings.maxRate")} hint={t("settings.maxRateHint")} optional={t("app.optional")}>
                {(id, d) => <Input id={id} aria-describedby={d} inputMode="decimal" value={form.max_rate_monthly ?? ""} onChange={(e) => set("max_rate_monthly", e.target.value.replace(/[^\d.]/g, "") || null)} />}
              </Field>
            </div>
          </Card>
          <Card>
            <h2 className="mb-1 text-lg">{t("settings.newLoans")}</h2>
            <p className="field-hint mb-3">{t("settings.newLoansHint")}</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={t("settings.ltvVehicle")}>
                {(id) => <Input id={id} inputMode="decimal" value={form.ltv_max_vehicle} onChange={(e) => set("ltv_max_vehicle", e.target.value.replace(/[^\d.]/g, ""))} />}
              </Field>
              <Field label={t("settings.ltvLand")}>
                {(id) => <Input id={id} inputMode="decimal" value={form.ltv_max_land} onChange={(e) => set("ltv_max_land", e.target.value.replace(/[^\d.]/g, ""))} />}
              </Field>
              <Field label={t("options.rounding")}>
                {(id) => (
                  <Select id={id} value={String(Number(form.emi_rounding_default) < 1 ? "0.01" : Number(form.emi_rounding_default))}
                    onChange={(e) => set("emi_rounding_default", e.target.value)}>
                    {["0.01", "1", "5", "10", "50", "100"].map((v) => (
                      <option key={v} value={v}>{v === "0.01" ? t("options.noRounding") : t("options.roundTo", { step: v })}</option>
                    ))}
                  </Select>
                )}
              </Field>
              <Field label={t("options.advance")}>
                {(id) => (
                  <Select id={id} value={String(form.advance_installments_default)} onChange={(e) => set("advance_installments_default", Number(e.target.value))}>
                    {[0, 1, 2, 3].map((v) => <option key={v} value={v}>{v}</option>)}
                  </Select>
                )}
              </Field>
              <Field label={t("options.oddFirst")} className="sm:col-span-2">
                {(id) => (
                  <Select id={id} value={form.broken_period_default} onChange={(e) => set("broken_period_default", e.target.value as AppSettings["broken_period_default"])}>
                    {(["first_installment", "upfront", "none"] as const).map((v) => <option key={v} value={v}>{t(`options.odd_${v}`)}</option>)}
                  </Select>
                )}
              </Field>
              <Field label={t("settings.processingFee")}>
                {(id) => <Input id={id} inputMode="decimal" value={form.processing_fee_percent} onChange={(e) => set("processing_fee_percent", e.target.value.replace(/[^\d.]/g, ""))} />}
              </Field>
              <Field label={t("settings.documentCharges")}>
                {(id) => <MoneyInput id={id} value={form.document_charges_default} onChange={(v) => set("document_charges_default", v || "0")} />}
              </Field>
            </div>
          </Card>
          <Card>
            <h2 className="mb-3 text-lg">{t("settings.penalty")}</h2>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label={t("loan.penaltyTitle")}>
                {(id) => (
                  <Select id={id} value={form.penalty_default_mode} onChange={(e) => set("penalty_default_mode", e.target.value as AppSettings["penalty_default_mode"])}>
                    <option value="off">{t("loan.penaltyOff")}</option><option value="per_day">{t("loan.penaltyPerDay")}</option><option value="pct_month">{t("loan.penaltyPct")}</option>
                  </Select>
                )}
              </Field>
              <Field label={t("loan.penaltyValue")}>{(id) => <Input id={id} inputMode="decimal" value={form.penalty_default_value} onChange={(e) => set("penalty_default_value", e.target.value.replace(/[^\d.]/g, ""))} />}</Field>
              {num("penalty_grace_days", t("loan.graceDays"))}
            </div>
          </Card>
          <Card>
            <h2 className="mb-3 text-lg">{t("settings.files")} · {t("settings.privacy")}</h2>
            <div className="grid gap-3 sm:grid-cols-3">
              {num("max_upload_mb", t("settings.maxUpload"))}
              {num("max_files_per_owner", t("settings.maxFiles"))}
              {num("retention_years", t("settings.retention"))}
            </div>
          </Card>
          <Card>
            <h2 className="mb-3 text-lg">{t("settings.staff")}</h2>
            <div className="space-y-2">
              <Switch checked={form.staff_enabled} onCheckedChange={(v) => set("staff_enabled", v)} label={t("settings.staffEnabled")} />
              {form.staff_enabled && <Switch checked={form.staff_can_create_loans} onCheckedChange={(v) => set("staff_can_create_loans", v)} label={t("settings.staffLoans")} />}
              {form.staff_enabled && <StaffList />}
            </div>
          </Card>
          <CategoriesCard />
          <HealthCard />
          <Card>
            <h2 className="mb-3 text-lg">{t("settings.data")}</h2>
            <Button variant="outline" onClick={() => void openFile("/export/full.zip", undefined, true)}>{t("settings.fullExport")}</Button>
          </Card>
        </>
      )}
      </div>
      {isOwner && form && (
        dirty && (
            <div className="sticky bottom-20 z-10 md:bottom-4">
              <Button size="lg" className="w-full shadow-lg" loading={save.isPending} onClick={() => save.mutate(form)}>
                {t("settings.saveSettings")}
              </Button>
            </div>
        )
      )}
    </div>
  );
}

function PasswordCard() {
  const { t } = useTranslation();
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const change = useMutation({
    mutationFn: () => api.put("/auth/password", { current_password: current, new_password: next }),
    onSuccess: () => { setCurrent(""); setNext(""); toast({ text: t("app.saved") }); },
  });
  return (
    <Card>
      <h2 className="mb-3 text-lg">{t("settings.changePassword")}</h2>
      <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <Field label={t("settings.currentPassword")}>{(id) => <Input id={id} type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />}</Field>
        <Field label={t("settings.newPassword")} hint={t("auth.passwordRule")} error={change.error ? errorMessage(change.error) : undefined}>
          {(id, d) => <Input id={id} aria-describedby={d} type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />}
        </Field>
        <Button loading={change.isPending} disabled={!current || !next} onClick={() => change.mutate()}>{t("app.save")}</Button>
      </div>
    </Card>
  );
}

function TwoFactorCard({ enabled, onChange }: { enabled: boolean; onChange: () => void }) {
  const { t } = useTranslation();
  const [qr, setQr] = useState<string | null>(null);
  const [secret, setSecret] = useState("");
  const [code, setCode] = useState("");
  const begin = useMutation({
    mutationFn: () => api.post<{ secret: string; otpauth_uri: string }>("/auth/totp/setup"),
    onSuccess: async (r) => { setSecret(r.secret); setQr(await QRCode.toDataURL(r.otpauth_uri, { margin: 1, width: 220 })); },
  });
  const enable = useMutation({ mutationFn: () => api.post("/auth/totp/enable", { code }), onSuccess: () => { setQr(null); onChange(); } });
  const disable = useMutation({ mutationFn: () => api.post("/auth/totp/disable"), onSuccess: onChange });
  return (
    <Card>
      <h2 className="mb-2 text-lg">{t("settings.twoFactor")}: {enabled ? t("settings.twoFactorOn") : t("settings.twoFactorOff")}</h2>
      {!enabled && !qr && <Button variant="secondary" loading={begin.isPending} onClick={() => begin.mutate()}>{t("settings.twoFactorSetup")}</Button>}
      {qr && (
        <div className="space-y-3">
          <p>{t("settings.twoFactorScan")}</p>
          <img src={qr} alt="" className="h-56 w-56 rounded-xl bg-white p-2" />
          <p className="break-all font-mono text-sm">{secret}</p>
          <Field label={t("auth.totp")} error={enable.error ? errorMessage(enable.error) : undefined}>
            {(id, d) => <Input id={id} aria-describedby={d} inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} />}
          </Field>
          <Button loading={enable.isPending} disabled={code.length !== 6} onClick={() => enable.mutate()}>{t("app.confirm")}</Button>
        </div>
      )}
      {enabled && <Button variant="outline" loading={disable.isPending} onClick={() => disable.mutate()}>{t("settings.twoFactorDisable")}</Button>}
    </Card>
  );
}

function StaffList() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api.get<User[]>("/users") });
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const add = useMutation({
    mutationFn: () => api.post("/users", { name, phone, password }),
    onSuccess: () => { setName(""); setPhone(""); setPassword(""); void qc.invalidateQueries({ queryKey: ["users"] }); },
  });
  const toggle = useMutation({
    mutationFn: (u: User) => api.patch(`/users/${u.id}`, { is_active: !u.is_active }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["users"] }),
  });
  return (
    <div className="space-y-2">
      {users.data?.filter((u) => u.role === "staff").map((u) => (
        <div key={u.id} className="flex items-center justify-between rounded-xl border border-line p-3">
          <span>{u.name} · {u.phone}</span>
          <Button size="sm" variant="outline" onClick={() => toggle.mutate(u)}>{u.is_active ? t("status.active") : t("status.blocked")}</Button>
        </div>
      ))}
      <div className="grid gap-2 sm:grid-cols-4 sm:items-end">
        <Field label={t("auth.name")}>{(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
        <Field label={t("auth.phone")}>{(id) => <Input id={id} type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />}</Field>
        <Field label={t("auth.password")}>{(id) => <Input id={id} type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />}</Field>
        <Button loading={add.isPending} disabled={!name || !phone || !password} onClick={() => add.mutate()}>{t("settings.addStaff")}</Button>
      </div>
      {add.error && <p className="field-error">{errorMessage(add.error)}</p>}
    </div>
  );
}

function CategoriesCard() {
  const { t } = useTranslation();
  const lang = useLang();
  const qc = useQueryClient();
  const cats = useQuery({ queryKey: ["categories", "all"], queryFn: () => api.get<Category[]>("/categories", { include_inactive: true }) });
  const [nameEn, setNameEn] = useState("");
  const [nameTa, setNameTa] = useState("");
  const [kind, setKind] = useState<"expense" | "income">("expense");
  const refresh = () => qc.invalidateQueries({ queryKey: ["categories"] });
  const add = useMutation({ mutationFn: () => api.post("/categories", { name_en: nameEn, name_ta: nameTa, kind, sort_order: 100 }),
    onSuccess: () => { setNameEn(""); setNameTa(""); void refresh(); } });
  const toggle = useMutation({ mutationFn: (c: Category) => api.put(`/categories/${c.id}`, { ...c, is_active: !c.is_active }), onSuccess: () => void refresh() });
  return (
    <Card>
      <h2 className="mb-3 text-lg">{t("settings.categories")}</h2>
      <ul className="mb-3 flex flex-wrap gap-2">
        {cats.data?.map((c) => (
          <li key={c.id}>
            <button onClick={() => toggle.mutate(c)} aria-pressed={c.is_active}
              className={`min-h-touch rounded-full border px-3 text-sm ${c.is_active ? "border-line bg-surface" : "border-dashed border-line text-muted line-through"}`}>
              {c.kind === "income" ? "+ " : "− "}{lang === "ta" ? c.name_ta : c.name_en}
            </button>
          </li>
        ))}
      </ul>
      <div className="grid gap-2 sm:grid-cols-4 sm:items-end">
        <Field label={t("borrower.nameEn")}>{(id) => <Input id={id} value={nameEn} onChange={(e) => setNameEn(e.target.value)} />}</Field>
        <Field label={t("borrower.nameTa")}>{(id) => <Input id={id} value={nameTa} onChange={(e) => setNameTa(e.target.value)} />}</Field>
        <Field label={t("cash.category")}>
          {(id) => <Select id={id} value={kind} onChange={(e) => setKind(e.target.value as "expense" | "income")}><option value="expense">{t("settings.expense")}</option><option value="income">{t("settings.income")}</option></Select>}
        </Field>
        <Button disabled={!nameEn || !nameTa} loading={add.isPending} onClick={() => add.mutate()}>{t("settings.addCategory")}</Button>
      </div>
    </Card>
  );
}

function HealthCard() {
  const { t } = useTranslation();
  const status = useQuery({ queryKey: ["status"], queryFn: () => api.get<{ jobs: { name: string; status: string; run_date: string | null }[];
    backup: { status: string; finished_at?: string; detail?: string } }>("/settings/status") });
  const [push, setPush] = useState("");
  const enablePush = async () => {
    try {
      const { key } = await api.get<{ key: string | null }>("/push/vapid-public-key");
      if (!key || !("serviceWorker" in navigator)) { setPush("—"); return; }
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
      await api.post("/push/subscribe", sub.toJSON());
      setPush(t("app.saved"));
    } catch (err) {
      setPush(errorMessage(err));
    }
  };
  return (
    <Card>
      <h2 className="mb-3 text-lg">{t("settings.health")}</h2>
      <ul className="space-y-1">
        <li>{t("settings.lastBackup")}: <b>{status.data?.backup.status ?? "…"}</b> {status.data?.backup.finished_at ? dmy(status.data.backup.finished_at) : ""}</li>
        {status.data?.jobs.map((j) => (
          <li key={j.name}>{j.name === "nightly" ? t("settings.nightly") : t("settings.notifications")}: <b>{j.status === "never" ? t("settings.never") : j.status}</b> {j.run_date ? dmy(j.run_date) : ""}</li>
        ))}
      </ul>
      <div className="mt-3 flex items-center gap-3">
        <Button variant="outline" onClick={() => void enablePush()}>{t("settings.notifications")}: {t("settings.enableNotifications")}</Button>
        {push && <span className="text-sm text-muted">{push}</span>}
      </div>
    </Card>
  );
}
