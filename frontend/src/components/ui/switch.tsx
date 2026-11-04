import * as S from "@radix-ui/react-switch";
import { useId, type ReactNode } from "react";

interface Props {
  checked: boolean;
  onCheckedChange: (value: boolean) => void;
  label: ReactNode;
  hint?: ReactNode;
}

export function Switch({ checked, onCheckedChange, label, hint }: Props) {
  const id = useId();
  return (
    <div className="flex items-start justify-between gap-4 rounded-xl border border-line bg-surface p-3">
      <label htmlFor={id} className="min-w-0 cursor-pointer">
        <span className="block font-semibold">{label}</span>
        {hint && <span className="block text-sm text-muted">{hint}</span>}
      </label>
      <S.Root id={id} checked={checked} onCheckedChange={onCheckedChange}
        className="relative mt-1 h-8 w-14 shrink-0 rounded-full bg-line transition-colors data-[state=checked]:bg-brand">
        <S.Thumb className="block h-6 w-6 translate-x-1 rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-7" />
      </S.Root>
    </div>
  );
}
