import { Link, useLocation } from "react-router-dom";
import { FolderKanban, PanelLeftClose, PanelLeftOpen, X } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Primary navigation — navy sidebar (DESIGN.md §8.1).
 *
 * Minimal & honest: only routes that actually exist are listed. The backend
 * exposes no Templates / Equipment / Validation / Audit / Reports / Settings
 * endpoints, so those nav items are intentionally omitted rather than faked.
 */
export interface SidebarProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

const NAV_ITEMS = [
  {
    label: "Projects",
    to: "/projects",
    icon: FolderKanban,
    activePrefix: "/projects",
  },
] as const;

export function Sidebar({
  collapsed,
  onToggleCollapse,
  mobileOpen,
  onCloseMobile,
}: SidebarProps) {
  const { pathname } = useLocation();

  return (
    <>
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/40 md:hidden"
          aria-hidden="true"
          onClick={onCloseMobile}
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex flex-col bg-navy-900 text-text-on-navy transition-[width,transform] duration-150 ease-out md:static md:translate-x-0",
          collapsed ? "w-[72px]" : "w-[264px]",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
        aria-label="Primary navigation"
      >
        {/* Brand header */}
        <div
          className={cn(
            "flex h-[72px] shrink-0 items-center border-b border-white/10 px-4",
            collapsed && "justify-center px-0",
          )}
        >
          <div className="flex items-center gap-2.5 overflow-hidden">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-control bg-white/10 text-text-on-navy">
              <span className="text-sm font-bold tracking-tight">W</span>
            </div>
            {!collapsed && (
              <div className="flex flex-col leading-tight">
                <span className="text-sm font-semibold tracking-tight text-text-on-navy">
                  WABAG
                </span>
                <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-on-navy-muted">
                  RFQ Automation
                </span>
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={onCloseMobile}
            className="ml-auto flex h-8 w-8 items-center justify-center rounded-control text-text-on-navy-muted hover:bg-white/10 md:hidden"
            aria-label="Close navigation"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto px-3 py-4" aria-label="Sections">
          <ul className="flex flex-col gap-1">
            {NAV_ITEMS.map(({ label, to, icon: Icon, activePrefix }) => {
              const active = pathname.startsWith(activePrefix);
              return (
                <li key={to}>
                  <Link
                    to={to}
                    onClick={onCloseMobile}
                    className={cn(
                      "relative flex h-11 items-center gap-3 rounded-control px-3 text-sm font-medium transition-colors",
                      active
                        ? "bg-navy-700 text-white"
                        : "text-text-on-navy-muted hover:bg-white/[0.06] hover:text-text-on-navy",
                      collapsed && "justify-center px-0",
                    )}
                    title={collapsed ? label : undefined}
                    aria-current={active ? "page" : undefined}
                  >
                    {active && !collapsed && (
                      <span
                        className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-navy-600"
                        aria-hidden="true"
                      />
                    )}
                    <Icon className="h-5 w-5 shrink-0" />
                    {!collapsed && <span>{label}</span>}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        {/* Footer: user card + collapse control */}
        <div className="shrink-0 border-t border-white/10 p-3">
          <div
            className={cn(
              "flex items-center gap-3 rounded-control px-2 py-2",
              collapsed && "justify-center px-0",
            )}
          >
            <div
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-avatar text-xs font-semibold text-white"
              aria-hidden="true"
            >
              MS
            </div>
            {!collapsed && (
              <div className="flex flex-col leading-tight overflow-hidden">
                <span className="truncate text-sm font-medium text-text-on-navy">
                  Mohamed Sallam
                </span>
                <span className="truncate text-xs text-text-on-navy-muted">
                  Engineer
                </span>
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={onToggleCollapse}
            className={cn(
              "mt-1 hidden h-9 items-center gap-3 rounded-control px-3 text-sm text-text-on-navy-muted transition-colors hover:bg-white/[0.06] hover:text-text-on-navy md:flex",
              collapsed && "justify-center px-0",
            )}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand" : "Collapse"}
          >
            {collapsed ? (
              <PanelLeftOpen className="h-5 w-5" />
            ) : (
              <PanelLeftClose className="h-5 w-5" />
            )}
            {!collapsed && <span>Collapse</span>}
          </button>
        </div>
      </aside>
    </>
  );
}
