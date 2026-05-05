import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  KeyRound,
  Layers,
  Rocket,
  Image as ImageIcon,
  LogOut,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";

const items = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/tokens", label: "FB Accounts", icon: KeyRound },
  { to: "/bulk", label: "Bulk Actions", icon: Layers },
  { to: "/launch", label: "Autozaliv", icon: Rocket },
  { to: "/creatives", label: "Creatives", icon: ImageIcon },
];

export function Sidebar() {
  const { user, logout } = useAuth();

  return (
    <aside className="glass sticky top-0 flex h-screen w-64 flex-col border-r border-ink-200/60 dark:border-ink-700/60">
      <div className="flex h-16 items-center px-6">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-ink-900 to-ink-700 text-white shadow-card">
            <span className="text-xs font-bold">FB</span>
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold tracking-tight">
              Ads Controller
            </div>
            <div className="text-[11px] text-ink-500">v0.1</div>
          </div>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 px-3">
        {items.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                "group flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition-colors",
                "text-ink-700 hover:bg-ink-100/80 dark:text-ink-300 dark:hover:bg-ink-800",
                isActive &&
                  "bg-white text-ink-900 shadow-card dark:bg-ink-700 dark:text-ink-100",
              )
            }
          >
            <Icon className="h-4 w-4 flex-shrink-0" />
            <span className="font-medium tracking-tight">{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto border-t border-ink-200/60 p-3 dark:border-ink-700/60">
        <div className="mb-2 px-2">
          <div className="text-xs text-ink-500">Signed in as</div>
          <div className="text-sm font-medium tracking-tight text-ink-800 dark:text-ink-200">
            {user?.username ?? "—"}
          </div>
        </div>
        <button
          onClick={() => void logout()}
          className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm text-ink-700 transition-colors hover:bg-ink-100/80 dark:text-ink-300 dark:hover:bg-ink-800"
        >
          <LogOut className="h-4 w-4" />
          <span>Sign out</span>
        </button>
      </div>
    </aside>
  );
}
