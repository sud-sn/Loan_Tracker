import { useQueryClient } from "@tanstack/react-query";
import { BarChart3, ClipboardList, FileSpreadsheet, Home, LogOut, Menu, PanelLeftClose, PanelLeftOpen, Plus, ScrollText,
  Settings, Users, WifiOff, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { api } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { useOnline } from "@/hooks/useOnline";
import { cn } from "@/lib/utils";

import { GlobalSearch } from "./GlobalSearch";
import { LanguageSwitch } from "./LanguageSwitch";
import { QuickAddSheet, QuickActionsProvider } from "./QuickActions";
import { Sheet } from "./ui/dialog";

// Phone (< 768 px): bottom bar. Tablet (768-1023 px): a narrow rail of icons with short labels.
// Laptop and larger (1024 px+): the full menu, which the owner can fold into the rail; that choice is
// remembered in this browser. The full menu's width follows the screen (14-18 rem, and rem grows a
// little on very large screens), so the page beside it always gets the rest of the width.
const RAIL_KEY = "lt.sidebar";
type Variant = "bar" | "rail" | "full";

function readCollapsed(): boolean {
  try { return localStorage.getItem(RAIL_KEY) === "rail"; } catch { return false; }
}

function NavItem({ to, Icon, label, title, end, variant }:
  { to: string; Icon: LucideIcon; label: string; title?: string; end?: boolean; variant: Variant }) {
  return (
    <NavLink to={to} end={end} title={title}
      className={({ isActive }) => cn(
        "font-semibold",
        variant === "bar" && "flex min-h-touch min-w-0 flex-1 basis-0 flex-col items-center justify-center gap-0.5 rounded-xl px-0.5 text-center text-[12px]",
        variant === "rail" && "flex w-full flex-col items-center justify-center gap-1 rounded-xl px-0.5 py-2 text-center text-xs leading-tight [overflow-wrap:anywhere]",
        variant === "full" && "flex min-h-touch w-full items-center gap-3 rounded-xl px-3 text-left text-[15px]",
        variant === "bar" ? (isActive ? "text-brand" : "text-muted hover:text-ink")
          // Active item: Solviz blue tint with a yellow marker on the left.
          : isActive ? "bg-brand-soft text-brand shadow-[inset_3px_0_0_rgb(var(--accent))]" : "text-muted hover:bg-sunken hover:text-ink",
      )}>
      <Icon className={cn("shrink-0", variant === "full" ? "h-5 w-5" : "h-6 w-6")} aria-hidden />
      <span className={cn(variant === "full" ? "min-w-0 leading-tight" : "leading-tight")}>{label}</span>
    </NavLink>
  );
}

export function AppShell() {
  const { t } = useTranslation();
  const { me, isOwner } = useAuth();
  const online = useOnline();
  const [addOpen, setAddOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const laptop = useMediaQuery("(min-width: 1024px)");
  const rail = !laptop || collapsed;
  const qc = useQueryClient();
  const navigate = useNavigate();
  const signOut = async () => {
    await api.post("/auth/logout").catch(() => undefined);
    qc.clear();
    qc.setQueryData(["me"], null);
    navigate("/login");
  };
  const toggleRail = () => setCollapsed((c) => {
    try { localStorage.setItem(RAIL_KEY, c ? "full" : "rail"); } catch { /* private window: not remembered */ }
    return !c;
  });

  const links = [
    { to: "/", end: true, label: t("nav.home"), short: t("nav.home"), Icon: Home, owner: false, main: true },
    { to: "/borrowers", label: t("nav.borrowers"), short: t("nav.borrowersShort"), Icon: Users, owner: false, main: true },
    { to: "/loans", label: t("nav.loans"), short: t("nav.loans"), Icon: ClipboardList, owner: false, main: true },
    { to: "/reports", label: t("nav.reports"), short: t("nav.reports"), Icon: BarChart3, owner: true, main: false },
    { to: "/import", label: t("nav.import"), short: t("nav.importShort"), Icon: FileSpreadsheet, owner: true, main: false },
    { to: "/audit", label: t("nav.audit"), short: t("nav.auditShort"), Icon: ScrollText, owner: true, main: false },
    { to: "/settings", label: t("nav.settings"), short: t("nav.settings"), Icon: Settings, owner: false, main: false },
  ].filter((l) => isOwner || !l.owner);
  const moreLinks = links.filter((l) => !l.main);

  return (
    <QuickActionsProvider>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:bg-surface focus:p-3">
        {t("app.skipToContent")}
      </a>
      <div className="min-h-dvh md:flex">
        <aside data-sidebar={rail ? "rail" : "full"}
          className={cn(
            "hidden shrink-0 border-r border-line bg-surface md:sticky md:top-0 md:flex md:h-dvh md:flex-col md:overflow-y-auto",
            "transition-[width] duration-200",
            rail ? "w-[7rem] p-2" : "w-[clamp(14rem,14vw,18rem)] p-3",
          )}>
          <div className={cn("mb-3 flex items-center gap-2 py-2", rail ? "justify-center" : "px-2")}>
            <img src="/favicon.svg" alt="" className="h-9 w-9 shrink-0" />
            {!rail && <span className="min-w-0 text-lg font-bold leading-tight text-brand">{t("app.name")}</span>}
          </div>
          <nav aria-label={t("nav.menu")} className="flex flex-col gap-1">
            {links.map((l) => (
              <NavItem key={l.to} to={l.to} end={l.end} Icon={l.Icon} variant={rail ? "rail" : "full"}
                label={rail ? l.short : l.label} title={rail ? l.label : undefined} />
            ))}
          </nav>
          <button onClick={() => setAddOpen(true)} title={rail ? t("nav.add") : undefined}
            className={cn("mt-3 flex shrink-0 items-center justify-center gap-2 bg-brand font-semibold text-brand-ink hover:bg-brand-strong active:scale-[.97]",
              rail ? "min-h-touch flex-col gap-0.5 rounded-xl px-1 py-2 text-xs" : "min-h-touch rounded-full px-4 text-sm")}>
            <Plus className="h-5 w-5" aria-hidden />{t("nav.add")}
          </button>
          {laptop && (
            <button onClick={toggleRail} aria-expanded={!rail}
              aria-label={rail ? t("nav.expandMenu") : t("nav.collapseMenu")} title={rail ? t("nav.expandMenu") : undefined}
              className={cn("mt-auto flex min-h-touch shrink-0 items-center gap-2 rounded-xl text-sm font-semibold text-muted hover:bg-sunken hover:text-ink",
                rail ? "justify-center" : "px-3")}>
              {rail ? <PanelLeftOpen className="h-5 w-5" aria-hidden />
                : <><PanelLeftClose className="h-5 w-5 shrink-0" aria-hidden /><span>{t("nav.collapseMenu")}</span></>}
            </button>
          )}
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-20 border-b border-line bg-bg/95 backdrop-blur">
            <div className="flex items-center gap-2 px-3 py-2 md:gap-3 md:px-5 lg:gap-4 lg:px-6 xl:px-8">
              <img src="/favicon.svg" alt="" className="h-8 w-8 md:hidden" />
              <div className="min-w-0 flex-1 md:max-w-xl lg:max-w-2xl"><GlobalSearch /></div>
              <div className="hidden flex-1 md:block" />
              <LanguageSwitch className="shrink-0" />
              <div className="hidden items-center gap-2 md:flex">
                <span className="hidden max-w-[12rem] truncate text-sm font-semibold lg:inline" title={me?.user.name}>{me?.user.name}</span>
                <button onClick={signOut} title={t("app.signOut")}
                  className="inline-flex min-h-touch min-w-touch items-center justify-center gap-2 rounded-full px-3 text-sm font-semibold hover:bg-sunken">
                  <LogOut className="h-5 w-5" aria-hidden /><span className="sr-only lg:not-sr-only">{t("app.signOut")}</span>
                </button>
              </div>
            </div>
            {!online && (
              <p role="status" className="flex items-center gap-2 bg-due-soft px-4 py-2 text-sm font-semibold text-due">
                <WifiOff className="h-4 w-4 shrink-0" aria-hidden />{t("app.offline")}
              </p>
            )}
          </header>
          {/* The page uses all the width it is given. Pages that need to react to their own width (for
              example when the menu is folded) use container queries on "main". */}
          <main id="main" className="@container/main safe-bottom mx-auto w-full max-w-[200rem] flex-1 px-3 pt-4 md:px-5 md:pt-5 lg:px-6 lg:pt-6 xl:px-8">
            <Outlet />
          </main>
        </div>
      </div>

      <nav aria-label={t("nav.menu")} data-bottom-nav
        className="fixed inset-x-0 bottom-0 z-30 flex items-stretch gap-1 border-t border-line bg-surface px-2 pb-[env(safe-area-inset-bottom)] pt-1 md:hidden">
        <NavItem to="/" end Icon={Home} label={t("nav.home")} variant="bar" />
        <NavItem to="/borrowers" Icon={Users} label={t("nav.borrowersShort")} variant="bar" />
        <div className="flex min-w-0 flex-1 basis-0 items-start justify-center">
          <button onClick={() => setAddOpen(true)} aria-label={t("nav.add")}
            className="-mt-5 inline-flex h-14 w-14 items-center justify-center rounded-full bg-accent text-accent-ink shadow-lg ring-4 ring-bg">
            <Plus className="h-7 w-7" aria-hidden />
          </button>
        </div>
        <NavItem to="/loans" Icon={ClipboardList} label={t("nav.loans")} variant="bar" />
        <button onClick={() => setMoreOpen(true)}
          className="flex min-h-touch min-w-0 flex-1 basis-0 flex-col items-center justify-center gap-0.5 text-[12px] font-semibold text-muted">
          <Menu className="h-6 w-6 shrink-0" aria-hidden /><span>{t("nav.more")}</span>
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
