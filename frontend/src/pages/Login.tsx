import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useNavigate } from "react-router-dom";

import { ApiError, api } from "@/api/client";
import type { Me } from "@/api/types";
import { LanguageSwitch } from "@/components/LanguageSwitch";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { useAuth } from "@/hooks/useAuth";
import { errorMessage } from "@/i18n";

export function LoginPage() {
  const { t, i18n } = useTranslation();
  const { me } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const setup = useQuery({ queryKey: ["setup"], queryFn: () => api.get<{ needs_setup: boolean }>("/auth/setup") });
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [needTotp, setNeedTotp] = useState(false);
  const firstRun = setup.data?.needs_setup;
  const submit = useMutation({
    mutationFn: () => firstRun
      ? api.post<Me>("/auth/setup", { name, phone, password, language: i18n.language })
      : api.post<Me>("/auth/login", { phone, password, totp: totp || undefined }),
    onSuccess: (data) => {
      qc.setQueryData(["me"], data);
      navigate("/");
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "TOTP_REQUIRED") setNeedTotp(true);
    },
  });
  if (me) return <Navigate to="/" replace />;
  const error = submit.error && !(submit.error instanceof ApiError && submit.error.code === "TOTP_REQUIRED" && !totp)
    ? errorMessage(submit.error) : undefined;
  return (
    <div className="flex min-h-dvh flex-col bg-bg">
      <div className="flex justify-end p-3"><LanguageSwitch /></div>
      <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center px-4 pb-16">
        <div className="mb-6 flex items-center gap-3">
          <img src="/favicon.svg" alt="" className="h-12 w-12" />
          <div>
            <h1 className="text-2xl text-brand">{t("app.name")}</h1>
            <p className="text-muted">{firstRun ? t("auth.setupIntro") : t("auth.signInTitle")}</p>
          </div>
        </div>
        <form className="card space-y-4 p-5" onSubmit={(e) => { e.preventDefault(); submit.mutate(); }}>
          {firstRun && (
            <Field label={t("auth.name")}>
              {(id) => <Input id={id} autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} required />}
            </Field>
          )}
          <Field label={t("auth.phone")}>
            {(id) => <Input id={id} type="tel" inputMode="numeric" autoComplete="username" value={phone}
              onChange={(e) => setPhone(e.target.value)} required />}
          </Field>
          <Field label={t("auth.password")} hint={firstRun ? t("auth.passwordRule") : undefined}
            error={needTotp ? undefined : error}>
            {(id, d) => <Input id={id} aria-describedby={d} type="password" value={password}
              autoComplete={firstRun ? "new-password" : "current-password"} onChange={(e) => setPassword(e.target.value)} required />}
          </Field>
          {needTotp && (
            <Field label={t("auth.totp")} hint={t("auth.totpHint")} error={error}>
              {(id, d) => <Input id={id} aria-describedby={d} inputMode="numeric" autoComplete="one-time-code" autoFocus
                value={totp} onChange={(e) => setTotp(e.target.value.replace(/\D/g, "").slice(0, 6))} />}
            </Field>
          )}
          <Button type="submit" size="lg" className="w-full" loading={submit.isPending}>
            {firstRun ? t("auth.createOwner") : t("auth.signIn")}
          </Button>
        </form>
      </main>
    </div>
  );
}
