import type { ReactNode } from "react";
import "./AppShell.css";

interface AppShellProps {
  sidebar: ReactNode;
  topbar: ReactNode;
  children: ReactNode;
}

export function AppShell({ sidebar, topbar, children }: AppShellProps) {
  return (
    <div className="app-shell">
      <aside className="app-sidebar">{sidebar}</aside>
      <section className="app-main">
        <header className="app-topbar">{topbar}</header>
        <main className="app-content">{children}</main>
      </section>
    </div>
  );
}
