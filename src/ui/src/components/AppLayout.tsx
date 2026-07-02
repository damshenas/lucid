import { useMemo, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { LogOut } from "lucide-react";
import { IconButton } from "./ui/IconButton";
import { Sidebar } from "./Sidebar";
import { BottomNav } from "./BottomNav";
import { MoreSheet } from "./MoreSheet";
import { NAV_ITEMS } from "../lib/nav";
import { hasPermission } from "../lib/permissions";
import type { Role } from "../lib/permissions";

interface Props {
  role: Role | null;
  onLogout: () => void;
}

const PRIMARY_COUNT = 3;

export function AppLayout({ role, onLogout }: Props) {
  const location = useLocation();
  const [moreOpen, setMoreOpen] = useState(false);

  const items = useMemo(
    () => NAV_ITEMS.filter((item) => hasPermission(role, item.permission)),
    [role],
  );
  const primary = items.slice(0, PRIMARY_COUNT);
  const overflow = items.slice(PRIMARY_COUNT);

  const title =
    items.find((item) =>
      item.path === "/" ? location.pathname === "/" : location.pathname.startsWith(item.path),
    )?.label ?? "Lucid";

  return (
    <div className="min-h-screen md:pl-60">
      <Sidebar items={items} />

      <header className="glass sticky top-0 z-10 flex items-center justify-between px-4 py-3 sm:px-6 md:px-8">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-gradient-to-r from-violet to-cyan md:hidden" />
          <span className="text-lg font-semibold tracking-tight">
            Lucid <span className="text-white/40 font-normal">/ {title}</span>
          </span>
        </div>
        <div className="flex items-center gap-3">
          {role && (
            <span className="hidden rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs uppercase tracking-wide text-white/50 sm:inline">
              {role}
            </span>
          )}
          <IconButton icon={<LogOut size={18} />} label="Log out" onClick={onLogout} />
        </div>
      </header>

      <main className="mx-auto max-w-2xl px-4 pb-28 pt-4 sm:px-6 md:max-w-5xl md:px-8 md:pb-10">
        <Outlet />
      </main>

      <BottomNav
        items={primary}
        moreItems={overflow}
        onMore={() => setMoreOpen(true)}
      />
      <MoreSheet open={moreOpen} items={overflow} onClose={() => setMoreOpen(false)} />
    </div>
  );
}
