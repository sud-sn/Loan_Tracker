import { forwardRef, useEffect, useState } from "react";

import { useLang } from "@/i18n";
import { amountInWords, groupWhileTyping, parseMoney } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Props {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  describedBy?: string;
  placeholder?: string;
  autoFocus?: boolean;
  className?: string;
  showWords?: boolean;
  name?: string;
}

/**
 * Money field: numeric keypad, Indian grouping while typing, and the amount in words below in
 * the current language so an extra zero is easy to spot (PRD section 10). ``value`` is the plain
 * decimal string ("100000.50").
 */
export const MoneyInput = forwardRef<HTMLInputElement, Props>(
  ({ id, value, onChange, describedBy, placeholder, autoFocus, className, showWords = true, name }, ref) => {
    const lang = useLang();
    const [display, setDisplay] = useState(() => (value ? groupWhileTyping(value) : ""));
    useEffect(() => {
      if (parseMoney(display) !== value) setDisplay(value ? groupWhileTyping(value) : "");
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [value]);
    const words = showWords ? amountInWords(value, lang) : "";
    return (
      <div>
        <div className="relative">
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-lg text-muted" aria-hidden>₹</span>
          <input
            ref={ref} id={id} name={name} inputMode="decimal" autoComplete="off" enterKeyHint="done"
            className={cn("control pl-8 text-lg font-semibold tabular", className)}
            value={display} placeholder={placeholder ?? "0"} aria-describedby={describedBy} autoFocus={autoFocus}
            onChange={(e) => {
              const next = groupWhileTyping(e.target.value);
              setDisplay(next);
              onChange(parseMoney(next));
            }}
          />
        </div>
        {words && <p className="mt-1 text-sm text-muted" aria-live="polite">{words}</p>}
      </div>
    );
  },
);
MoneyInput.displayName = "MoneyInput";
