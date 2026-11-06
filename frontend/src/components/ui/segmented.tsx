import { useId } from "react";

import { cn } from "@/lib/utils";

interface Option<T extends string> {
  value: T;
  label: string;
  hint?: string;
}

interface Props<T extends string> {
  label?: string;
  value: T;
  options: Option<T>[];
  onChange: (value: T) => void;
  columns?: 2 | 3 | 4;
}

/** Radio buttons that look like large tiles; easy to hit with a thumb. */
export function Segmented<T extends string>({ label, value, options, onChange, columns }: Props<T>) {
  const name = useId();
  const cols = { 2: "grid-cols-2", 3: "grid-cols-1 sm:grid-cols-3", 4: "grid-cols-2 sm:grid-cols-4" }[columns ?? 2];
  return (
    <fieldset className="min-w-0">
      {label && <legend className="field-label">{label}</legend>}
      <div className={cn("grid gap-2", cols)}>
        {options.map((o) => (
          <label key={o.value}
            className={cn("flex min-h-touch min-w-0 cursor-pointer flex-col justify-center rounded-[10px] border px-3 py-1.5",
              value === o.value ? "border-brand bg-brand-soft text-brand" : "border-line bg-surface hover:bg-sunken")}>
            <input type="radio" className="sr-only" name={name} value={o.value} checked={value === o.value}
              onChange={() => onChange(o.value)} />
            {/* Long Tamil words may break inside a word rather than spill out of the tile. */}
            <span className="font-semibold [overflow-wrap:anywhere]">{o.label}</span>
            {o.hint && <span className="text-sm text-muted [overflow-wrap:anywhere]">{o.hint}</span>}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
