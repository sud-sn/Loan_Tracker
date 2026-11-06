import * as D from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}

/** A bottom sheet on phones, a centred dialog on larger screens. */
export function Sheet({ open, onOpenChange, title, description, children, footer, wide }: Props) {
  const { t } = useTranslation();
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-ink/40 backdrop-blur-[1px]" />
        <D.Content
          className={cn(
            "fixed z-50 flex max-h-[92dvh] w-full flex-col bg-surface shadow-xl outline-none",
            "inset-x-0 bottom-0 rounded-t-2xl sm:inset-auto sm:left-1/2 sm:top-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2",
            "sm:rounded-2xl", wide ? "sm:max-w-3xl" : "sm:max-w-lg",
          )}
        >
          <div className="flex items-start justify-between gap-3 border-b border-line px-4 py-3 sm:px-6">
            <div className="min-w-0">
              <D.Title className="text-lg font-semibold">{title}</D.Title>
              {description && <D.Description className="text-sm text-muted">{description}</D.Description>}
            </div>
            <D.Close className="-mr-2 inline-flex min-h-touch min-w-touch items-center justify-center rounded-full hover:bg-sunken"
              aria-label={t("app.close")}>
              <X className="h-5 w-5" aria-hidden />
            </D.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-6">{children}</div>
          {footer && (
            <div className="flex flex-wrap justify-end gap-2 border-t border-line px-4 py-3 pb-[calc(env(safe-area-inset-bottom)+12px)] sm:px-6">
              {footer}
            </div>
          )}
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
