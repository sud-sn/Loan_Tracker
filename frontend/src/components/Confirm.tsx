import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { errorMessage } from "@/i18n";

import { Button } from "./ui/button";
import { Sheet } from "./ui/dialog";
import { Field, Textarea } from "./ui/field";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  body?: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  reasonLabel?: string;
  onConfirm: (reason: string) => Promise<unknown>;
}

/** Confirm before anything that cannot be undone (PRD section 10); optional mandatory reason. */
export function ConfirmSheet({ open, onOpenChange, title, body, confirmLabel, danger, reasonLabel, onConfirm }: Props) {
  const { t } = useTranslation();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = async () => {
    setBusy(true);
    setError("");
    try {
      await onConfirm(reason.trim());
      setReason("");
      onOpenChange(false);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title={title}
      footer={<>
        <Button variant="outline" onClick={() => onOpenChange(false)}>{t("app.cancel")}</Button>
        <Button variant={danger ? "danger" : "primary"} loading={busy} onClick={run}
          disabled={!!reasonLabel && reason.trim().length < 3}>{confirmLabel}</Button>
      </>}>
      <div className="space-y-4">
        {body && <div className="text-ink">{body}</div>}
        {reasonLabel && (
          <Field label={reasonLabel} error={error}>
            {(id, d) => <Textarea id={id} aria-describedby={d} value={reason} onChange={(e) => setReason(e.target.value)} />}
          </Field>
        )}
        {!reasonLabel && error && <p role="alert" className="field-error">{error}</p>}
      </div>
    </Sheet>
  );
}
