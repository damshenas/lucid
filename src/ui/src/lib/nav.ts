import type { ComponentType } from "react";
import {
  Briefcase,
  CandlestickChart,
  FlaskConical,
  LayoutDashboard,
  LineChart,
  Radio,
  Receipt,
  Settings as SettingsIcon,
  ShieldCheck,
} from "lucide-react";
import type { Permission, Role } from "./permissions";

export interface NavItem {
  path: string;
  label: string;
  icon: ComponentType<{ size?: number; strokeWidth?: number }>;
  permission: Permission;
}

export const NAV_ITEMS: NavItem[] = [
  { path: "/", label: "Dashboard", icon: LayoutDashboard, permission: "view_trading" },
  { path: "/positions", label: "Positions", icon: Briefcase, permission: "view_trading" },
  { path: "/signals", label: "Signals", icon: Radio, permission: "view_trading" },
  { path: "/orders", label: "Orders", icon: Receipt, permission: "view_trading" },
  { path: "/prices", label: "Prices", icon: CandlestickChart, permission: "view_trading" },
  {
    path: "/strategies",
    label: "Strategies",
    icon: LineChart,
    permission: "edit_own_strategies",
  },
  {
    path: "/backtesting",
    label: "Backtesting",
    icon: FlaskConical,
    permission: "edit_own_strategies",
  },
  { path: "/settings", label: "Settings", icon: SettingsIcon, permission: "change_password" },
  { path: "/admin", label: "Admin", icon: ShieldCheck, permission: "manage_users" },
];

/** Explicit landing route per role (admin has no view_trading, so "/" would 404 for them). */
export function defaultPathFor(role: Role | null): string {
  if (role === "admin") return "/admin";
  if (role === "trader" || role === "viewer") return "/";
  return "/settings";
}
