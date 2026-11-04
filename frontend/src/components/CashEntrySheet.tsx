import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "@/api/client";
import type { Category } from "@/api/types";
import { errorMessage, useLang } from "@/i18n";
import { todayIST } from "@/lib/format";
import { cn, newKey } from "@/lib/utils";

import { DateInput } from "./DateInput";
import { MoneyInput } from "./MoneyInput";
import { Button } from "./ui/button";
import { Sheet } from "./ui/dialog";
import { Field, Input, Select } from "./ui/field";
import { useToast } from "./ui/toast";

interface Existing {
  id: string;
  version: number;
  amount: string;
  category_id?: string;
  note: string | null;
  mode: string;
  entry_date: string;
}

/** An expense in under 10 seconds: amount, category, done. Date defaults to today, mode to cash. */
export function CashEntrySheet({ direction, onClose, existing }: { direction: "in" | "out"; onClose: () => void;
  existing?: Existing }) {
  const { t } = useTranslation();
  const lang = useLang();
  const qc = useQueryClient();
  const toast = useToast();
  const cats = useQuery({ queryKey: ["categories"], queryFn: () => api.get<Category[]>("/categories") });
  const options = (cats.data ?? []).filter((c) => c.kind === (direction === "out" ? "expense" : "income"));
  const [amount, setAmount] = useState(existing?.amount ?? "");
  const [category, setCategory] = useState(existing?.category_id ?? "");
  const [note, setNote] = useState(existing?.note ?? "");
  const [mode, setMode] = useState(existing?.mode ?? "cash");
  const [date, setDate] = useState(existing?.entry_date ?? todayIST());
  const [key] = useState(() => newKey("cash"));
  const chosen = category || options[0]?.id || "";
  const save = useMutation({
    mutationFn: () => existing
      ? api.patch(`/cash-entries/${existing.id}`, { version: existing.version, amount, category_id: chosen, note, mode,
        entry_date: date })
      : api.post("/cash-entries", { direction, amount, category_id: chosen, note: note || null, mode, entry_date: date,
        idempotency_key: key }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["daybook"] });
      toast({ text: t("app.saved") });
      onClose();
    },
  });
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}
      title={existing ? t("cash.editTitle") : direction === "out" ? t("cash.expenseTitle") : t("cash.incomeTitle")}
      footer={<>
        <Button variant="outline" onClick={onClose}>{t("app.cancel")}</Button>
        <Button size="lg" loading={save.isPending} disabled={!amount || !chosen} onClick={() => save.mutate()}>
          {t("app.save")}
        </Button>
      </>}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <Field label={t("cash.amount")} error={save.error ? errorMessage(save.error) : undefined}>
          {(id, d) => <MoneyInput id={id} describedBy={d} value={amount} onChange={setAmount} autoFocus />}
        </Field>
        <fieldset>
          <legend className="field-label">{t("cash.category")}</legend>
          <div className="flex flex-wrap gap-2">
            {options.map((c) => (
              <button key={c.id} type="button" onClick={() => setCategory(c.id)} aria-pressed={chosen === c.id}
                className={cn("min-h-touch rounded-full border px-4 font-semibold",
                  chosen === c.id ? "border-brand bg-brand text-brand-ink" : "border-line bg-surface")}>
                {lang === "ta" ? c.name_ta : c.name_en}
              </button>
            ))}
          </div>
        </fieldset>
        <Field label={t("cash.note")} optional={t("app.optional")}>
          {(id) => <Input id={id} value={note ?? ""} onChange={(e) => setNote(e.target.value)} />}
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("cash.date")}>
            {(id) => <DateInput id={id} max={todayIST()} value={date} onChange={setDate} />}
          </Field>
          <Field label={t("cash.mode")}>
            {(id) => (
              <Select id={id} value={mode} onChange={(e) => setMode(e.target.value)}>
                {["cash", "upi", "bank", "other"].map((m) => <option key={m} value={m}>{t(`mode.${m}`)}</option>)}
              </Select>
            )}
          </Field>
        </div>
        <button type="submit" className="hidden" />
      </form>
    </Sheet>
  );
}
