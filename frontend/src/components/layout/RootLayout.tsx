import { Outlet } from "react-router-dom";

import { Header } from "./Header";

/** App shell: top nav + routed page content via <Outlet/>. */
export function RootLayout() {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container py-6">
        <Outlet />
      </main>
    </div>
  );
}
