import { useQueryClient } from "@tanstack/react-query";
import { BarChart3, ClipboardList, FileSpreadsheet, Home, LogOut, Menu, Plus, ScrollText, Settings, Users,
  WifiOff } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { api } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { useOnline } from "@/hooks/useOnline";
import { cn } from "@/lib/utils";

import { GlobalSearch } from "./GlobalSearch";
import { LanguageSwitch } from "./LanguageSwitch";
import { QuickAddSheet, QuickActionsProvider } from "./QuickActions";
import { Sheet } from "./ui/dialog";

function NavItem({ to, icon, label, end }: { to: string; icon: ReactNode; label: string; end?: boolean }) {
  return (
    <NavLink to={to} end={end}
      className={({ isActive }) => cn(
        "flex min-h-touch min-w-0 flex-1 basis-0 flex-col items-center justify-center gap-0.5 rounded-xl px-0.5 text-center text-[12px] font-semibold",
        "lg:flex-none lg:flex-row lg:justify-start lg:gap-3 lg:px-3 lg:text-base",
        isActive ? "text-brand lg:bg-brand-soft" : "text-muted hover:text-ink",
      )}>
      {icon}
      <span className="leading-tight">{label}</span>
    </NavLink>
  );
}

export function AppShell() {
  const { t } = useTranslation();
  const { me, isOwner } = useAuth();
  const online = useOnline();
  const [addOpen, setAddOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const signOut = async () => {
    await api.post("/auth/logout").catch(() => undefined);
    qc.clear();
    qc.setQueryData(["me"], null);
    navigate("/login");
  };
  const icon = "h-6 w-6 shrink-0";
  const moreLinks = [
    { to: "/reports", label: t("nav.reports"), Icon: BarChart3, owner: true },
    { to: "/import", label: t("nav.import"), Icon: FileSpreadsheet, owner: true },
    { to: "/audit", label: t("nav.audit"), Icon: ScrollText, owner: true },
    { to: "/settings", label: t("nav.settings"), Icon: Settings, owner: false },
  ].filter((l) => isOwner || !l.owner);

  return (
    <QuickActionsProvider>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:bg-surface focus:p-3">
        {t("app.skipToContent")}
      </a>
      <div className="min-h-dvh lg:grid lg:grid-cols-[248px_1fr]">
        <aside className="hidden border-r border-line bg-surface lg:flex lg:flex-col lg:gap-1 lg:p-3">
          <div className="mb-3 flex items-center gap-2 px-2 py-2">
            <img src="/favicon.svg" alt="" className="h-9 w-9" />
            <span className="text-lg font-bold text-brand">{t("app.name")}</span>
          </div>
          <NavItem to="/" end icon={<Home className={icon} aria-hidden />} label={t("nav.home")} />
          <NavItem to="/borrowers" icon={<Users className={icon} aria-hidden />} label={t("nav.borrowers")} />
          <NavItem to="/loans" icon={<ClipboardList className={icon} aria-hidden />} label={t("nav.loans")} />
          {moreLinks.map((l) => <NavItem key={l.to} to={l.to} icon={<l.Icon className={icon} aria-hidden />} label={l.label} />)}
          <button onClick={() => setAddOpen(true)}
            className="mt-3 flex min-h-touch items-center justify-center gap-2 rounded-xl bg-brand px-3 font-semibold text-brand-ink">
            <Plus className="h-5 w-5" aria-hidden />{t("nav.add")}
          </button>
          <div className="mt-auto space-y-2 px-2 pt-4 text-sm text-muted">
            <p className="truncate">{me?.user.name}</p>
            <button onClick={signOut} className="flex min-h-touch items-center gap-2 font-semibold text-ink">
              <LogOut className="h-5 w-5" aria-hidden />{t("app.signOut")}
            </button>
          </div>
        </aside>

        <div className="min-w-0">
          <header className="sticky top-0 z-20 border-b border-line bg-bg/95 backdrop-blur">
            <div className="mx-auto flex max-w-5xl items-center gap-2 px-3 py-2 lg:px-6">
              <img src="/favicon.svg" alt="" className="h-8 w-8 lg:hidden" />
              <GlobalSearch />
              <LanguageSwitch className="shrink-0" />
            </div>
            {!online && (
              <p role="status" className="flex items-center gap-2 bg-due-soft px-4 py-2 text-sm font-semibold text-due">
                <WifiOff className="h-4 w-4 shrink-0" aria-hidden />{t("app.offline")}
              </p>
            )}
          </header>
          <main id="main" className="safe-bottom mx-auto max-w-5xl px-3 pt-4 lg:px-6">
            <Outlet />
          </main>
        </div>
      </div>

      <nav aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-30 flex items-stretch gap-1 border-t border-line bg-surface px-2 pb-[env(safe-area-inset-bottom)] pt-1 lg:hidden">
        <NavItem to="/" end icon={<Home className={icon} aria-hidden />} label={t("nav.home")} />
        <NavItem to="/borrowers" icon={<Users className={icon} aria-hidden />} label={t("nav.borrowersShort")} />
        <div className="flex min-w-0 flex-1 basis-0 items-start justify-center">
          <button onClick={() => setAddOpen(true)} aria-label={t("nav.add")}
            className="-mt-5 inline-flex h-14 w-14 items-center justify-center rounded-full bg-brand text-brand-ink shadow-lg ring-4 ring-bg">
            <Plus className="h-7 w-7" aria-hidden />
          </button>
        </div>
        <NavItem to="/loans" icon={<ClipboardList className={icon} aria-hidden />} label={t("nav.loans")} />
        <button onClick={() => setMoreOpen(true)}
          className="flex min-h-touch min-w-0 flex-1 basis-0 flex-col items-center justify-center gap-0.5 text-[12px] font-semibold text-muted">
          <Menu className={icon} aria-hidden /><span>{t("nav.more")}</span>
        </button>
      </nav>

      <QuickAddSheet open={addOpen} onOpenChange={setAddOpen} />
      <Sheet open={moreOpen} onOpenChange={setMoreOpen} title={t("nav.more")}>
        <div className="grid gap-2">
          {moreLinks.map((l) => (
            <NavLink key={l.to} to={l.to} onClick={() => setMoreOpen(false)}
              className="flex min-h-touch items-center gap-3 rounded-xl border border-line px-4 py-3 font-semibold">
              <l.Icon className="h-5 w-5 text-brand" aria-hidden />{l.label}
            </NavLink>
          ))}
          <button onClick={signOut} className="flex min-h-touch items-center gap-3 rounded-xl border border-line px-4 py-3 font-semibold">
            <LogOut className="h-5 w-5 text-brand" aria-hidden />{t("app.signOut")}
          </button>
        </div>
      </Sheet>
    </QuickActionsProvider>
  );
}
