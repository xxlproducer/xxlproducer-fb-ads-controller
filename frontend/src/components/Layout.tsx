import type { ReactNode } from "react";
import { Sidebar } from "./Sidebar";

interface LayoutProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}

export function Layout({ title, description, actions, children }: LayoutProps) {
  return (
    <div className="flex min-h-screen bg-ink-50 dark:bg-ink-900">
      <Sidebar />
      <main className="flex-1 overflow-x-hidden">
        <header className="glass sticky top-0 z-10 border-b border-ink-200/60 dark:border-ink-700/60">
          <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-8">
            <div className="min-w-0">
              <h1 className="truncate text-xl font-semibold tracking-tight">
                {title}
              </h1>
              {description && (
                <p className="truncate text-xs text-ink-500">{description}</p>
              )}
            </div>
            {actions && <div className="flex-shrink-0">{actions}</div>}
          </div>
        </header>
        <div className="mx-auto max-w-6xl animate-slide-up px-8 py-8">
          {children}
        </div>
      </main>
    </div>
  );
}
