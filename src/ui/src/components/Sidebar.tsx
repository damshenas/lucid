import { NavLink } from "react-router-dom";
import type { NavItem } from "../lib/nav";

interface Props {
  items: NavItem[];
}

export function Sidebar({ items }: Props) {
  return (
    <aside className="glass fixed inset-y-0 left-0 z-20 hidden w-60 flex-col border-r border-white/10 px-3 py-6 md:flex">
      <div className="mb-6 flex items-center gap-2 px-3">
        <span className="h-2.5 w-2.5 rounded-full bg-gradient-to-r from-violet to-cyan" />
        <span className="bg-gradient-to-r from-violet via-white to-cyan bg-clip-text text-lg font-bold text-transparent">
          Lucid
        </span>
      </div>
      <nav className="flex flex-1 flex-col gap-1">
        {items.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            end={path === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200
              ${
                isActive
                  ? "bg-white/10 text-white glow-violet"
                  : "text-white/60 hover:bg-white/5 hover:text-white/90"
              }`
            }
          >
            <Icon size={18} strokeWidth={2} />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
