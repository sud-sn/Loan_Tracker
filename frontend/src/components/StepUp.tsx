import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { api, setStepUpHandler } from "@/api/client";
import { errorMessage } from "@/i18n";

import { Button } from "./ui/button";
import { Sheet } from "./ui/dialog";
import { Field, Input } from "./ui/field";

/** When the server asks for step-up (reveal Aadhaar, reverse, export…), ask for the password. */
export function StepUpProvider({ children, totpEnabled }: { children: ReactNode; totpEnabled: boolean }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const resolver = useRef<((ok: boolean) => void) | null>(null);

  useEffect(() => {
    setStepUpHandler(
      () =>
        new Promise<boolean>((resolve) => {
          resolver.current = resolve;
          setPassword("");
          setCode("");
          setError("");
          setOpen(true);
        }),
    );
    return () => setStepUpHandler(null);
  }, []);

  const finish = (ok: boolean) => {
    resolver.current?.(ok);
    resolver.current = null;
    setOpen(false);
  };

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      await api.post("/auth/step-up", { password, totp: code || undefined });
      finish(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {children}
      <Sheet open={open} onOpenChange={(o) => !o && finish(false)} title={t("auth.stepUpTitle")}
        description={t("auth.stepUpIntro")}
        footer={<>
          <Button variant="outline" onClick={() => finish(false)}>{t("app.cancel")}</Button>
          <Button onClick={submit} loading={busy} disabled={!password}>{t("auth.confirm")}</Button>
        </>}>
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
          <Field label={t("auth.password")} error={error}>
            {(id, d) => <Input id={id} aria-describedby={d} type="password" autoComplete="current-password" autoFocus
              value={password} onChange={(e) => setPassword(e.target.value)} />}
          </Field>
          {totpEnabled && (
            <Field label={t("auth.totp")}>
              {(id) => <Input id={id} inputMode="numeric" autoComplete="one-time-code" value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} />}
            </Field>
          )}
          <button type="submit" className="hidden" />
        </form>
      </Sheet>
    </>
  );
}
