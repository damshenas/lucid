import { NavLink } from "react-router-dom";
import { X } from "lucide-react";
import type { NavItem } from "../lib/nav";
import { IconButton } from "./ui/IconButton";

interface Props {
  open: boolean;
  items: NavItem[];
  onClose: () => void;
}

export function MoreSheet({ open, items, onClose }: Props) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-30 md:hidden">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="glass animate-fade-in-up absolute inset-x-0 bottom-0 rounded-t-3xl p-4 pb-[calc(1rem+env(safe-area-inset-bottom))]">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-sm font-semibold uppercase tracking-wide text-white/40">
            More
          </span>
          <IconButton icon={<X size={18} />} label="Close" onClick={onClose} />
        </div>
        <div className="grid grid-cols-3 gap-3">
          {items.map(({ path, label, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              onClick={onClose}
              className={({ isActive }) =>
                `flex flex-col items-center gap-2 rounded-2xl border px-3 py-4 text-xs font-medium transition-colors
                ${
                  isActive
                    ? "border-violet/40 bg-violet/10 text-violet"
                    : "border-white/10 bg-white/5 text-white/70 hover:bg-white/10"
                }`
              }
            >
              <Icon size={20} strokeWidth={1.75} />
              {label}
            </NavLink>
          ))}
        </div>
      </div>
    </div>
  );
}
