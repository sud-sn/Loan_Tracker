import { useLang } from "@/i18n";
import { longDate } from "@/lib/format";

import { Input } from "./ui/field";

interface Props {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  min?: string;
  max?: string;
  describedBy?: string;
}

/** The phone's own date picker, with the date written out below as DD/MM/YYYY in the current language. */
export function DateInput({ id, value, onChange, min, max, describedBy }: Props) {
  const lang = useLang();
  return (
    <div>
      <Input id={id} type="date" value={value} min={min} max={max} aria-describedby={describedBy}
        onChange={(e) => onChange(e.target.value)} />
      {value && <p className="mt-1 text-sm text-muted">{longDate(value, lang)}</p>}
    </div>
  );
}
