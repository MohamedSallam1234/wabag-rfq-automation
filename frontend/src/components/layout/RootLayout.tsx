import { useState } from "react";
import { Outlet } from "react-router-dom";

import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

/**
 * App shell: fixed navy sidebar + fluid content column (header + routed page
 * + footer). Sidebar collapse (desktop) and off-canvas drawer (mobile) state
 * live here so the header hamburger and the sidebar stay in sync.
 */
export function RootLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed((c) => !c)}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header onOpenMobileSidebar={() => setMobileOpen(true)} />
        <main className="flex-1 p-6 md:p-8">
          <Outlet />
        </main>
        <footer className="flex flex-col items-center justify-between gap-1 border-t border-border px-6 py-4 text-xs text-text-muted sm:flex-row md:px-8">
          <span>VA Tech WABAG RFQ Automation System</span>
          <span>© {new Date().getFullYear()} All rights reserved.</span>
          <span>v1.0.0</span>
        </footer>
      </div>
    </div>
  );
}
