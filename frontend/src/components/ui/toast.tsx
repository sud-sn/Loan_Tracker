import { CheckCircle2, X } from "lucide-react";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

interface Toast {
  id: number;
  text: string;
  action?: { label: string; run: () => void };
  tone?: "ok" | "error";
}

const Ctx = createContext<(t: Omit<Toast, "id">) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const { t } = useTranslation();
  const push = useCallback((toast: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setItems((prev) => [...prev.slice(-2), { ...toast, id }]);
    setTimeout(() => setItems((prev) => prev.filter((x) => x.id !== id)), toast.action ? 8000 : 4000);
  }, []);
  return (
    <Ctx.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-24 z-[60] flex flex-col items-center gap-2 px-4 lg:bottom-6">
        {items.map((item) => (
          <div key={item.id} role="status"
            className={`pointer-events-auto flex w-full max-w-md items-center gap-3 rounded-xl px-4 py-3 text-white shadow-lg ${item.tone === "error" ? "bg-late" : "bg-ink"}`}>
            {item.tone !== "error" && <CheckCircle2 className="h-5 w-5 shrink-0" aria-hidden />}
            <span className="flex-1">{item.text}</span>
            {item.action && (
              <button className="min-h-touch rounded-lg px-3 font-semibold underline" onClick={() => {
                item.action?.run();
                setItems((prev) => prev.filter((x) => x.id !== item.id));
              }}>{item.action.label}</button>
            )}
            <button aria-label={t("app.close")} className="min-h-touch min-w-touch"
              onClick={() => setItems((prev) => prev.filter((x) => x.id !== item.id))}>
              <X className="mx-auto h-4 w-4" aria-hidden />
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export function useToast() {
  return useContext(Ctx);
}
