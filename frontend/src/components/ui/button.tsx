import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  // Solviz-style pill buttons: compact on a laptop, comfortable to tap on a phone.
  "btn inline-flex items-center justify-center gap-2 rounded-full font-semibold text-center leading-tight " +
    "transition-[background-color,border-color,color,transform] active:scale-[.97] " +
    "disabled:opacity-50 disabled:pointer-events-none select-none whitespace-normal",
  {
    variants: {
      variant: {
        primary: "border border-brand bg-brand text-brand-ink hover:border-brand-strong hover:bg-brand-strong",
        secondary: "border border-brand/25 bg-brand-soft text-brand hover:border-brand/50",
        outline: "border border-line-strong/60 bg-surface text-ink hover:border-line-strong hover:bg-sunken",
        ghost: "text-ink hover:bg-sunken",
        accent: "border border-accent bg-accent text-accent-ink hover:brightness-95",
        danger: "border border-late bg-late text-onfill hover:brightness-95",
        paid: "border border-paid bg-paid text-onfill hover:brightness-95",
      },
      size: {
        md: "min-h-touch px-4 py-2 text-[15px] md:text-sm",
        lg: "min-h-[48px] px-5 py-2.5 text-base md:min-h-[44px] md:text-[15px]",
        icon: "min-h-touch min-w-touch p-2",
        sm: "min-h-[38px] px-3 py-1.5 text-sm md:min-h-[34px] md:text-[13px]",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, children, disabled, type = "button", ...props }, ref) => (
    <button ref={ref} type={type} className={cn(buttonVariants({ variant, size }), className)}
      disabled={disabled || loading} aria-busy={loading || undefined} {...props}>
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  ),
);
Button.displayName = "Button";

export { buttonVariants };
