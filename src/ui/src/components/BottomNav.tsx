import { NavLink } from "react-router-dom";
import { MoreHorizontal } from "lucide-react";
import type { NavItem } from "../lib/nav";

interface Props {
  items: NavItem[];
  moreItems?: NavItem[];
  onMore?: () => void;
}

export function BottomNav({ items, moreItems = [], onMore }: Props) {
  return (
    <nav
      className="glass fixed inset-x-0 bottom-0 z-20 pb-[env(safe-area-inset-bottom)] md:hidden"
      aria-label="Primary"
    >
      <div className="mx-auto flex max-w-2xl items-stretch justify-around px-2">
        {items.map(({ path, label, icon: Icon, disabled }) =>
          disabled ? (
            <span
              key={path}
              aria-disabled="true"
              title="Temporarily disabled"
              className="flex flex-1 cursor-not-allowed flex-col items-center gap-1 py-3 text-xs font-medium text-white/25"
            >
              <Icon size={22} strokeWidth={1.75} />
              <span>{label}</span>
            </span>
          ) : (
            <NavLink
              key={path}
              to={path}
              end={path === "/"}
              className={({ isActive }) =>
                `flex flex-1 flex-col items-center gap-1 py-3 text-xs font-medium
                transition-all duration-200 outline-none
                ${isActive ? "text-violet" : "text-white/50 hover:text-white/80"}`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon size={22} strokeWidth={isActive ? 2.25 : 1.75} />
                  <span
                    className={`transition-transform duration-200 ${isActive ? "scale-105" : ""}`}
                  >
                    {label}
                  </span>
                </>
              )}
            </NavLink>
          ),
        )}
        {moreItems.length > 0 && (
          <button
            onClick={onMore}
            className="flex flex-1 flex-col items-center gap-1 py-3 text-xs font-medium text-white/50
              outline-none transition-all duration-200 hover:text-white/80"
          >
            <MoreHorizontal size={22} strokeWidth={1.75} />
            <span>More</span>
          </button>
        )}
      </div>
    </nav>
  );
}
