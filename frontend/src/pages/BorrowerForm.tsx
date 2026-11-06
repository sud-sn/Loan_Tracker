import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, api } from "@/api/client";
import type { AppSettings, Borrower, BorrowerDetail } from "@/api/types";
import { NameFields } from "@/components/NameFields";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Segmented } from "@/components/ui/segmented";
import { ErrorState, ListSkeleton } from "@/components/ui/states";
import { useAuth } from "@/hooks/useAuth";
import { errorMessage } from "@/i18n";
import { formatAadhaarInput, isValidAadhaar, isValidPhone } from "@/lib/verhoeff";

interface Guarantor { name: string; phone: string; relation: string }

/** Create or edit a borrower. Used as a page and inline from the new-loan flow. */
export function BorrowerForm({ onSaved, inline }: { onSaved?: (b: Borrower) => void; inline?: boolean }) {
  const { t } = useTranslation();
  const { id } = useParams();
  const editing = !!id && !inline;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { isOwner } = useAuth();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.get<AppSettings>("/settings") });
  const existing = useQuery({ queryKey: ["borrower", id], enabled: editing,
    queryFn: () => api.get<BorrowerDetail>(`/borrowers/${id}`) });
  const [names, setNames] = useState({ nameEn: "", nameTa: "" });
  const [relation, setRelation] = useState("");
  const [phone, setPhone] = useState("");
  const [altPhone, setAltPhone] = useState("");
  const [aadhaar, setAadhaar] = useState("");
  const [address, setAddress] = useState("");
  const [profile, setProfile] = useState({ occupation: "", town: "", district: "", pincode: "" });
  const [language, setLanguage] = useState<"en" | "ta">("ta");
  const [status, setStatus] = useState("active");
  const [notes, setNotes] = useState("");
  const [guarantors, setGuarantors] = useState<Guarantor[]>([]);
  const [consent, setConsent] = useState(false);
  const [consentMethod, setConsentMethod] = useState<"verbal" | "signed">("verbal");
  const [noticeOpen, setNoticeOpen] = useState(false);
  const [duplicate, setDuplicate] = useState<ApiError | null>(null);
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    const b = existing.data;
    if (!b) return;
    setNames({ nameEn: b.name_en ?? "", nameTa: b.name_ta ?? "" });
    setRelation(b.relation_name ?? "");
    setPhone(b.phone ?? "");
    setAltPhone(b.alt_phone ?? "");
    setAddress(b.address ?? "");
    setProfile({ occupation: b.occupation ?? "", town: b.town ?? "", district: b.district ?? "", pincode: b.pincode ?? "" });
    setLanguage(b.preferred_language);
    setStatus(b.status);
    setNotes(b.notes ?? "");
    setGuarantors(b.guarantors.map((g) => ({ name: g.name, phone: g.phone ?? "", relation: g.relation ?? "" })));
  }, [existing.data]);
  useEffect(() => {
    if (settings.data && !editing) setLanguage(settings.data.default_language);
  }, [settings.data, editing]);

  const aadhaarDigits = aadhaar.replace(/\D/g, "");
  const errors = {
    name: !names.nameEn.trim() && !names.nameTa.trim() ? t("errors.NAME_REQUIRED") : undefined,
    phone: !isValidPhone(phone) ? t("errors.PHONE_INVALID") : undefined,
    aadhaar: editing && !aadhaarDigits ? undefined
      : aadhaarDigits.length !== 12 ? t("errors.AADHAAR_FORMAT")
      : !isValidAadhaar(aadhaarDigits) ? t("errors.AADHAAR_CHECKSUM") : undefined,
    address: !address.trim() ? t("errors.REQUIRED") : undefined,
    consent: !editing && !consent ? t("errors.CONSENT_REQUIRED") : undefined,
  };
  const valid = Object.values(errors).every((e) => !e);

  const save = useMutation({
    mutationFn: (confirmDuplicate: boolean) => {
      const common = {
        name_en: names.nameEn || null, name_ta: names.nameTa || null, relation_name: relation || null, phone,
        alt_phone: altPhone || null, address, preferred_language: language, notes: notes || null,
        occupation: profile.occupation || null, town: profile.town || null, district: profile.district || null,
        pincode: profile.pincode || null,
        guarantors: guarantors.filter((g) => g.name.trim()).map((g) => ({ name: g.name, phone: g.phone || null,
          relation: g.relation || null })),
        confirm_duplicate: confirmDuplicate,
      };
      return editing
        ? api.patch<Borrower>(`/borrowers/${id}`, { ...common, version: existing.data?.version, status,
          ...(aadhaarDigits ? { aadhaar: aadhaarDigits } : {}) })
        : api.post<Borrower>("/borrowers", { ...common, aadhaar: aadhaarDigits,
          consent: { given: consent, method: consentMethod, language } });
    },
    onSuccess: (b) => {
      setDuplicate(null);
      void qc.invalidateQueries({ queryKey: ["borrowers"] });
      void qc.invalidateQueries({ queryKey: ["borrower", b.id] });
      if (onSaved) onSaved(b);
      else navigate(`/borrowers/${b.id}`, { replace: true });
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "DUPLICATE_BORROWER") setDuplicate(err);
    },
  });

  if (editing && existing.isLoading) return <ListSkeleton rows={2} />;
  if (editing && existing.isError) return <ErrorState error={existing.error} />;
  const show = (e?: string) => (touched ? e : undefined);
  const years = settings.data?.retention_years ?? 8;
  return (
    <form className={inline ? "space-y-5" : "mx-auto max-w-[110rem] space-y-5"} noValidate onSubmit={(e) => {
      e.preventDefault();
      setTouched(true);
      if (valid) save.mutate(false);
    }}>
      {!inline && <h1 className="text-2xl">{editing ? t("borrower.editTitle") : t("borrower.newTitle")}</h1>}
      {/* Laptop: personal details on the left; language, guarantor, notes and consent on the right. */}
      <div className={inline ? "space-y-5" : "grid items-start gap-x-8 gap-y-5 xl:grid-cols-2"}>
        <div className="min-w-0 space-y-5">
          <NameFields nameEn={names.nameEn} nameTa={names.nameTa} onChange={setNames} error={show(errors.name)} />
          <Field label={t("borrower.relation")} optional={t("app.optional")}>
            {(fid) => <Input id={fid} value={relation} onChange={(e) => setRelation(e.target.value)} />}
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("borrower.phone")} error={show(errors.phone)}>
              {(fid, d) => <Input id={fid} aria-describedby={d} type="tel" inputMode="numeric" autoComplete="off" value={phone}
                onChange={(e) => setPhone(e.target.value.replace(/[^\d+ ]/g, ""))} />}
            </Field>
            <Field label={t("borrower.altPhone")} optional={t("app.optional")}>
              {(fid) => <Input id={fid} type="tel" inputMode="numeric" value={altPhone} onChange={(e) => setAltPhone(e.target.value)} />}
            </Field>
          </div>
          <Field label={t("borrower.aadhaar")} error={show(errors.aadhaar)}
            hint={editing ? `${existing.data?.aadhaar_masked ?? ""} · ${t("borrower.aadhaarKeep")}` : t("borrower.aadhaarHint")}>
            {(fid, d) => (
              <>
                <Input id={fid} aria-describedby={d} inputMode="numeric" autoComplete="off" value={aadhaar}
                  className="tabular tracking-wider" placeholder="XXXX XXXX XXXX"
                  onChange={(e) => setAadhaar(formatAadhaarInput(e.target.value))} />
                {aadhaarDigits.length === 12 && isValidAadhaar(aadhaarDigits) && (
                  <p className="mt-1 inline-flex items-center gap-1 text-sm font-semibold text-paid">
                    <CheckCircle2 className="h-4 w-4" aria-hidden />{t("borrower.aadhaarChecked")}
                  </p>
                )}
              </>
            )}
          </Field>
          <Field label={t("borrower.address")} error={show(errors.address)}>
            {(fid, d) => <Textarea id={fid} aria-describedby={d} value={address} onChange={(e) => setAddress(e.target.value)} />}
          </Field>
          {/* Plain details used for reports by place and occupation (never Aadhaar or phone). */}
          <div className="grid gap-3 sm:grid-cols-2">
            {(["town", "district", "occupation", "pincode"] as const).map((k) => (
              <Field key={k} label={t(`borrower.${k}`)} optional={t("app.optional")}>
                {(fid) => <Input id={fid} value={profile[k]} inputMode={k === "pincode" ? "numeric" : undefined}
                  maxLength={k === "pincode" ? 6 : 80}
                  onChange={(e) => setProfile({ ...profile, [k]: k === "pincode" ? e.target.value.replace(/\D/g, "") : e.target.value })} />}
              </Field>
            ))}
          </div>
        </div>
        <div className="min-w-0 space-y-5">
          <Segmented label={t("borrower.language")} value={language} onChange={setLanguage}
            options={[{ value: "ta", label: "தமிழ்" }, { value: "en", label: "English" }]} />
          {editing && (
            <Field label={t("borrower.statusLabel")}>
              {(fid) => (
                <Select id={fid} value={status} onChange={(e) => setStatus(e.target.value)}>
                  {["active", "blocked", "closed"].map((s) => <option key={s} value={s}>{t(`status.${s}`)}</option>)}
                </Select>
              )}
            </Field>
          )}
          <fieldset className="space-y-3">
            <legend className="field-label">{t("borrower.guarantor")}</legend>
            {guarantors.map((g, i) => (
              <div key={i} className="grid gap-2 rounded-xl border border-line p-3 sm:grid-cols-[1fr_1fr_1fr_auto]">
                <Input aria-label={t("borrower.guarantorName")} placeholder={t("borrower.guarantorName")} value={g.name}
                  onChange={(e) => setGuarantors((gs) => gs.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
                <Input aria-label={t("borrower.guarantorPhone")} placeholder={t("borrower.guarantorPhone")} type="tel"
                  value={g.phone} onChange={(e) => setGuarantors((gs) => gs.map((x, j) => (j === i ? { ...x, phone: e.target.value } : x)))} />
                <Input aria-label={t("borrower.guarantorRelation")} placeholder={t("borrower.guarantorRelation")}
                  value={g.relation} onChange={(e) => setGuarantors((gs) => gs.map((x, j) => (j === i ? { ...x, relation: e.target.value } : x)))} />
                <Button size="icon" variant="ghost" aria-label={t("app.delete")}
                  onClick={() => setGuarantors((gs) => gs.filter((_, j) => j !== i))}><Trash2 className="h-5 w-5" aria-hidden /></Button>
              </div>
            ))}
            {guarantors.length < 5 && (
              <Button variant="outline" size="sm" onClick={() => setGuarantors((gs) => [...gs, { name: "", phone: "", relation: "" }])}>
                <Plus className="h-4 w-4" aria-hidden />{t("borrower.addGuarantor")}
              </Button>
            )}
          </fieldset>
          <Field label={t("borrower.notes")} optional={t("app.optional")}>
            {(fid) => <Textarea id={fid} value={notes} onChange={(e) => setNotes(e.target.value)} />}
          </Field>
          {!editing && (
            <fieldset className="space-y-3 rounded-2xl border border-line bg-sunken/50 p-4">
              <legend className="px-1 font-semibold">{t("borrower.consentTitle")}</legend>
              <button type="button" className="min-h-touch font-semibold text-brand underline" onClick={() => setNoticeOpen(true)}>
                {t("borrower.showNotice")}
              </button>
              <Segmented label={t("borrower.consentMethod")} value={consentMethod} onChange={setConsentMethod}
                options={[{ value: "verbal", label: t("borrower.consentVerbal") }, { value: "signed", label: t("borrower.consentSigned") }]} />
              <label className="flex min-h-touch cursor-pointer items-start gap-3">
                <input type="checkbox" className="mt-1 h-6 w-6 accent-[rgb(var(--brand))]" checked={consent}
                  onChange={(e) => setConsent(e.target.checked)} />
                <span>{t("borrower.consentNotice")}</span>
              </label>
              {show(errors.consent) && <p role="alert" className="field-error">{errors.consent}</p>}
            </fieldset>
          )}
        </div>
      </div>
      {save.error && !duplicate && <ErrorState error={save.error} />}
      <div className="flex gap-2 xl:justify-end">
        {!inline && <Button variant="outline" onClick={() => navigate(-1)}>{t("app.cancel")}</Button>}
        <Button type="submit" size="lg" className="flex-1 xl:min-w-[12rem] xl:flex-none" loading={save.isPending}>{t("app.save")}</Button>
      </div>

      <Sheet open={noticeOpen} onOpenChange={setNoticeOpen} title={t("borrower.consentTitle")}>
        <div className="space-y-4">
          <p lang="ta">{t("consentText.ta", { years })}</p>
          <p lang="en">{t("consentText.en", { years })}</p>
        </div>
      </Sheet>
      <Sheet open={!!duplicate} onOpenChange={(o) => !o && setDuplicate(null)} title={t("borrower.duplicateTitle")}
        footer={<>
          <Button variant="outline" onClick={() => setDuplicate(null)}>{t("app.cancel")}</Button>
          {isOwner && <Button variant="danger" loading={save.isPending} onClick={() => save.mutate(true)}>{t("borrower.duplicateProceed")}</Button>}
        </>}>
        <p>{duplicate?.params.match === "aadhaar"
          ? t("borrower.duplicateAadhaar", { codes: duplicate?.params.matches })
          : t("borrower.duplicatePhone", { codes: duplicate?.params.matches })}</p>
        {!isOwner && <p className="mt-2 text-muted">{t("borrower.duplicateOwnerOnly")}</p>}
        {save.error && duplicate && save.error !== duplicate && <p className="field-error">{errorMessage(save.error)}</p>}
      </Sheet>
    </form>
  );
}
