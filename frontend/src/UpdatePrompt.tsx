import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

let listener: ((apply: () => void) => void) | null = null;
let pending: (() => void) | null = null;

export function offerUpdate(apply: () => void): void {
  pending = apply;
  listener?.(apply);
}

export function UpdatePrompt() {
  const { t } = useTranslation();
  const [apply, setApply] = useState<(() => void) | null>(() => pending);
  useEffect(() => {
    listener = (fn) => setApply(() => fn);
    return () => { listener = null; };
  }, []);
  if (!apply) return null;
  return (
    <div role="status" className="fixed inset-x-3 top-3 z-[70] mx-auto flex max-w-md items-center justify-between gap-3 rounded-xl bg-ink px-4 py-3 text-white shadow-lg">
      <span>{t("app.updateReady")}</span>
      <Button size="sm" variant="secondary" onClick={apply}>{t("app.reload")}</Button>
    </div>
  );
}
