import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "btn inline-flex items-center justify-center gap-2 rounded-xl font-semibold text-center transition-colors " +
    "disabled:opacity-50 disabled:pointer-events-none select-none whitespace-normal",
  {
    variants: {
      variant: {
        primary: "bg-brand text-brand-ink hover:bg-brand/90 active:bg-brand/80",
        secondary: "bg-brand-soft text-brand hover:bg-brand-soft/80",
        outline: "border border-line bg-surface text-ink hover:bg-sunken",
        ghost: "text-ink hover:bg-sunken",
        danger: "bg-late text-white hover:bg-late/90",
        paid: "bg-paid text-white hover:bg-paid/90",
      },
      size: {
        md: "min-h-touch px-4 py-2 text-base",
        lg: "min-h-[56px] px-5 py-3 text-lg",
        icon: "min-h-touch min-w-touch p-2",
        sm: "min-h-[40px] px-3 py-1.5 text-sm",
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
