import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Search, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api } from "@/api/client";
import type { SearchResult } from "@/api/types";
import { useDebounced } from "@/hooks/useOnline";
import { useLang } from "@/i18n";
import { displayName, money } from "@/lib/format";

/** One search box on every screen: name (either script), code, phone, loan no., last 4 of Aadhaar. */
export function GlobalSearch() {
  const { t } = useTranslation();
  const lang = useLang();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const wrap = useRef<HTMLDivElement>(null);
  const debounced = useDebounced(q.trim(), 180);
  const digits = debounced.replace(/\D/g, "");
  const blocked = digits.length > 10; // never send a full Aadhaar number anywhere
  const { data, isFetching } = useQuery({
    queryKey: ["search", debounced],
    queryFn: () => api.get<SearchResult[]>("/search", { q: debounced }),
    enabled: debounced.length >= 1 && !blocked,
    staleTime: 30_000,
  });
  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const results = data ?? [];
  const go = (r: SearchResult) => {
    setOpen(false);
    setQ("");
    navigate(r.loan_id ? `/loans/${r.loan_id}` : `/borrowers/${r.borrower_id}`);
  };
  return (
    <div ref={wrap} className="relative w-full max-w-xl">
      <label htmlFor={`${listId}-input`} className="sr-only">{t("app.search")}</label>
      <Search className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-muted" aria-hidden />
      <input id={`${listId}-input`} type="search" role="combobox" aria-expanded={open && !!debounced}
        aria-controls={listId} aria-autocomplete="list" autoComplete="off" enterKeyHint="search"
        className="control pl-10 pr-10" placeholder={t("app.searchShort")} title={t("app.searchPlaceholder")} value={q}
        onChange={(e) => { setQ(e.target.value); setOpen(true); setActive(0); }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)); }
          if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
          if (e.key === "Enter" && results[active]) go(results[active]);
          if (e.key === "Escape") setOpen(false);
        }} />
      {q && (
        <button type="button" aria-label={t("app.close")} onClick={() => setQ("")}
          className="absolute right-1 top-1/2 inline-flex min-h-touch min-w-touch -translate-y-1/2 items-center justify-center">
          <X className="h-4 w-4" aria-hidden />
        </button>
      )}
      {open && debounced && (
        <ul id={listId} role="listbox"
          className="absolute left-0 right-0 top-full z-30 mt-1 max-h-[60vh] overflow-y-auto rounded-xl border border-line bg-surface p-1 shadow-xl">
          {blocked && <li className="p-3 text-sm text-late">{t("errors.SEARCH_TOO_MANY_DIGITS")}</li>}
          {!blocked && !isFetching && results.length === 0 && <li className="p-3 text-muted">{t("app.noResults")}</li>}
          {results.map((r, i) => (
            <li key={`${r.borrower_id}-${r.loan_id ?? ""}`} role="option" aria-selected={i === active}>
              <button type="button" onClick={() => go(r)} onMouseEnter={() => setActive(i)}
                className={`flex min-h-touch w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left ${i === active ? "bg-sunken" : ""}`}>
                <span className="min-w-0">
                  <span className="block truncate font-semibold">{displayName(lang, r.name_en, r.name_ta)}</span>
                  <span className="block text-sm text-muted">{r.code}{r.loan_no ? ` · ${r.loan_no}` : ""}{r.phone ? ` · ${r.phone}` : ""}</span>
                </span>
                <span className="shrink-0 text-right">
                  <span className="block tabular">{money(r.outstanding)}</span>
                  {r.overdue && (
                    <span className="inline-flex items-center gap-1 text-sm font-semibold text-late">
                      <AlertTriangle className="h-3.5 w-3.5" aria-hidden />{t("status.overdue")}
                    </span>
                  )}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
