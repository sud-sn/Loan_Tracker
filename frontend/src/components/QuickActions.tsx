import { useQuery } from "@tanstack/react-query";
import { HandCoins, MinusCircle, PlusCircle, UserPlus, Wallet } from "lucide-react";
import { createContext, lazy, Suspense, useContext, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api } from "@/api/client";
import type { SearchResult } from "@/api/types";
import { useDebounced } from "@/hooks/useOnline";
import { useLang } from "@/i18n";
import { displayName, money } from "@/lib/format";

// Loaded when first opened, to keep the first screen's script small.
const CashEntrySheet = lazy(() => import("./CashEntrySheet").then((m) => ({ default: m.CashEntrySheet })));
const RecordPaymentSheet = lazy(() => import("./RecordPaymentSheet").then((m) => ({ default: m.RecordPaymentSheet })));
import { Sheet } from "./ui/dialog";
import { Input } from "./ui/field";

interface QuickActions {
  receivePayment: (loanId?: string, amount?: string) => void;
  addCash: (direction: "in" | "out") => void;
}

const Ctx = createContext<QuickActions>({ receivePayment: () => undefined, addCash: () => undefined });

export function useQuickActions() {
  return useContext(Ctx);
}

export function QuickActionsProvider({ children }: { children: ReactNode }) {
  const [payment, setPayment] = useState<{ loanId?: string; amount?: string } | null>(null);
  const [cash, setCash] = useState<"in" | "out" | null>(null);
  return (
    <Ctx.Provider value={{
      receivePayment: (loanId, amount) => setPayment({ loanId, amount }),
      addCash: (direction) => setCash(direction),
    }}>
      {children}
      <Suspense fallback={null}>
      {payment && !payment.loanId && (
        <LoanPicker onPick={(loanId) => setPayment({ loanId })} onClose={() => setPayment(null)} />
      )}
      {payment?.loanId && (
        <RecordPaymentSheet loanId={payment.loanId} initialAmount={payment.amount} onClose={() => setPayment(null)} />
      )}
      {cash && <CashEntrySheet direction={cash} onClose={() => setCash(null)} />}
      </Suspense>
    </Ctx.Provider>
  );
}

function LoanPicker({ onPick, onClose }: { onPick: (loanId: string) => void; onClose: () => void }) {
  const { t } = useTranslation();
  const lang = useLang();
  const [q, setQ] = useState("");
  const debounced = useDebounced(q.trim(), 180);
  const { data } = useQuery({
    queryKey: ["pick-loan", debounced],
    queryFn: async () => {
      const results = await api.get<SearchResult[]>("/search", { q: debounced });
      const out: { loanId: string; label: string; sub: string }[] = [];
      for (const r of results.slice(0, 8)) {
        if (r.loan_id && r.loan_no) {
          out.push({ loanId: r.loan_id, label: displayName(lang, r.name_en, r.name_ta), sub: `${r.code} · ${r.loan_no}` });
          continue;
        }
        const loans = await api.get<{ items: { id: string; loan_no: string; stored_status: string; outstanding: string }[] }>(
          "/loans", { borrower_id: r.borrower_id, status: "active" });
        for (const l of loans.items) {
          out.push({ loanId: l.id, label: displayName(lang, r.name_en, r.name_ta), sub: `${r.code} · ${l.loan_no} · ${money(l.outstanding)}` });
        }
      }
      return out;
    },
    enabled: debounced.length >= 1 && debounced.replace(/\D/g, "").length <= 10,
  });
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={t("nav.receivePayment")}>
      <Input autoFocus placeholder={t("app.searchPlaceholder")} value={q} onChange={(e) => setQ(e.target.value)}
        aria-label={t("app.search")} />
      <ul className="mt-3 space-y-2">
        {(data ?? []).map((row) => (
          <li key={row.loanId}>
            <button onClick={() => onPick(row.loanId)}
              className="flex min-h-touch w-full flex-col items-start rounded-xl border border-line px-4 py-2 text-left hover:bg-sunken">
              <span className="font-semibold">{row.label}</span>
              <span className="text-sm text-muted">{row.sub}</span>
            </button>
          </li>
        ))}
      </ul>
    </Sheet>
  );
}

/** The central “+”: receive payment, give loan, add expense, add other income, add borrower. */
export function QuickAddSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qa = useQuickActions();
  const items = [
    { label: t("nav.receivePayment"), Icon: HandCoins, run: () => qa.receivePayment(), tone: "text-moneyin" },
    { label: t("nav.giveLoan"), Icon: Wallet, run: () => navigate("/loans/new"), tone: "text-moneyout" },
    { label: t("nav.addExpense"), Icon: MinusCircle, run: () => qa.addCash("out"), tone: "text-moneyout" },
    { label: t("nav.addIncome"), Icon: PlusCircle, run: () => qa.addCash("in"), tone: "text-moneyin" },
    { label: t("nav.addBorrower"), Icon: UserPlus, run: () => navigate("/borrowers/new"), tone: "text-brand" },
  ];
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title={t("nav.add")}>
      <div className="grid grid-cols-2 gap-3">
        {items.map((it) => (
          <button key={it.label} onClick={() => { onOpenChange(false); it.run(); }}
            className="flex min-h-[88px] flex-col items-center justify-center gap-2 rounded-2xl border border-line bg-surface p-3 text-center font-semibold hover:bg-sunken">
            <it.Icon className={`h-7 w-7 ${it.tone}`} aria-hidden />{it.label}
          </button>
        ))}
      </div>
    </Sheet>
  );
}

export function QuickAddButtons() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qa = useQuickActions();
  const items = [
    { label: t("nav.receivePayment"), Icon: HandCoins, run: () => qa.receivePayment(), cls: "bg-paid text-white" },
    { label: t("nav.giveLoan"), Icon: Wallet, run: () => navigate("/loans/new"), cls: "bg-brand text-brand-ink" },
    { label: t("nav.addExpense"), Icon: MinusCircle, run: () => qa.addCash("out"), cls: "bg-surface text-ink border border-line" },
    { label: t("nav.addIncome"), Icon: PlusCircle, run: () => qa.addCash("in"), cls: "bg-surface text-ink border border-line" },
  ];
  return (
    <div className="grid grid-cols-2 gap-2 @[44rem]/main:grid-cols-4">
      {items.map((it) => (
        <button key={it.label} onClick={it.run}
          className={`flex min-h-[64px] items-center justify-center gap-2 rounded-2xl px-3 py-2 text-center font-semibold shadow-card ${it.cls}`}>
          <it.Icon className="h-6 w-6 shrink-0" aria-hidden /><span>{it.label}</span>
        </button>
      ))}
    </div>
  );
}
