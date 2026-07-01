import { LayoutDashboard, LineChart, Settings as SettingsIcon } from "lucide-react";
import type { ComponentType } from "react";

interface Props {
  current: string;
  onNavigate: (view: string) => void;
}

interface Item {
  key: string;
  label: string;
  icon: ComponentType<{ size?: number; strokeWidth?: number }>;
}

const ITEMS: Item[] = [
  { key: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { key: "strategies", label: "Strategies", icon: LineChart },
  { key: "settings", label: "Settings", icon: SettingsIcon },
];

export function BottomNav({ current, onNavigate }: Props) {
  return (
    <nav
      className="glass fixed inset-x-0 bottom-0 z-20 pb-[env(safe-area-inset-bottom)]"
      aria-label="Primary"
    >
      <div className="mx-auto flex max-w-2xl items-stretch justify-around px-2">
        {ITEMS.map(({ key, label, icon: Icon }) => {
          const active = current === key;
          return (
            <button
              key={key}
              onClick={() => onNavigate(key)}
              aria-current={active ? "page" : undefined}
              className={`flex flex-1 flex-col items-center gap-1 py-3 text-xs font-medium
                transition-all duration-200 outline-none
                ${active ? "text-violet" : "text-white/50 hover:text-white/80"}`}
            >
              <Icon size={22} strokeWidth={active ? 2.25 : 1.75} />
              <span
                className={`transition-transform duration-200 ${active ? "scale-105" : ""}`}
              >
                {label}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
