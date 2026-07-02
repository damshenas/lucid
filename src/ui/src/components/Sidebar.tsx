import { NavLink } from "react-router-dom";
import { NAV_GROUP_ORDER, type NavItem } from "../lib/nav";

interface Props {
  items: NavItem[];
}

function groupItems(items: NavItem[]): [string, NavItem[]][] {
  const byGroup = new Map<string, NavItem[]>();
  for (const item of items) {
    const list = byGroup.get(item.group) ?? [];
    list.push(item);
    byGroup.set(item.group, list);
  }
  const ordered = [...byGroup.keys()].sort((a, b) => {
    const ia = NAV_GROUP_ORDER.indexOf(a);
    const ib = NAV_GROUP_ORDER.indexOf(b);
    return (ia === -1 ? NAV_GROUP_ORDER.length : ia) - (ib === -1 ? NAV_GROUP_ORDER.length : ib);
  });
  return ordered.map((group) => [group, byGroup.get(group)!]);
}

export function Sidebar({ items }: Props) {
  const groups = groupItems(items);

  return (
    <aside className="glass fixed inset-y-0 left-0 z-20 hidden w-60 flex-col overflow-y-auto border-r border-white/10 px-3 py-6 md:flex">
      <div className="mb-6 flex items-center gap-2 px-3">
        <span className="h-2.5 w-2.5 rounded-full bg-gradient-to-r from-violet to-cyan" />
        <span className="bg-gradient-to-r from-violet via-white to-cyan bg-clip-text text-lg font-bold text-transparent">
          Lucid
        </span>
      </div>
      <nav className="flex flex-1 flex-col gap-5">
        {groups.map(([group, groupItems]) => (
          <div key={group} className="flex flex-col gap-1">
            <span className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-white/30">
              {group}
            </span>
            {groupItems.map(({ path, label, icon: Icon }) => (
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
          </div>
        ))}
      </nav>
    </aside>
  );
}
