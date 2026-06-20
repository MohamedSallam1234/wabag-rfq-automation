import { Menu } from "lucide-react";

export interface HeaderProps {
  onOpenMobileSidebar: () => void;
}

/**
 * Top bar (DESIGN.md §8.2). Search, notifications and help are intentionally
 * omitted — there are no backend endpoints to back them. The user card is
 * static (no auth in the backend).
 */
export function Header({ onOpenMobileSidebar }: HeaderProps) {
  return (
    <header className="sticky top-0 z-20 flex h-[72px] shrink-0 items-center gap-3 border-b border-border bg-surface px-4 md:px-6">
      <button
        type="button"
        onClick={onOpenMobileSidebar}
        className="flex h-9 w-9 items-center justify-center rounded-control text-text-secondary hover:bg-surface-subtle md:hidden"
        aria-label="Open navigation"
      >
        <Menu className="h-5 w-5" />
      </button>

      <span className="text-base font-semibold text-text-primary">Projects</span>

      <div className="ml-auto flex items-center gap-3">
        <div className="hidden items-center gap-2.5 sm:flex">
          <div
            className="flex h-9 w-9 items-center justify-center rounded-full bg-avatar text-xs font-semibold text-white"
            aria-hidden="true"
          >
            MS
          </div>
          <div className="flex flex-col leading-tight">
            <span className="text-sm font-medium text-text-primary">
              Mohamed Sallam
            </span>
            <span className="text-xs text-text-muted">Engineer</span>
          </div>
        </div>
        <div
          className="flex h-9 w-9 items-center justify-center rounded-full bg-avatar text-xs font-semibold text-white sm:hidden"
          aria-hidden="true"
        >
          MS
        </div>
      </div>
    </header>
  );
}
