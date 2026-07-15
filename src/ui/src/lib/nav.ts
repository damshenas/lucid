import type { ComponentType } from "react";
import {
  Briefcase,
  CandlestickChart,
  Clock,
  FlaskConical,
  LayoutDashboard,
  LineChart,
  Receipt,
  Send,
  Settings as SettingsIcon,
  ShieldCheck,
  BarChart3,
  Users as UsersIcon,
} from "lucide-react";
import type { Permission, Role } from "./permissions";

export interface NavItem {
  path: string;
  label: string;
  icon: ComponentType<{ size?: number; strokeWidth?: number }>;
  permission: Permission;
  /** Function-based grouping used by the desktop sidebar (see components/Sidebar.tsx). */
  group: string;
  /** Shown but not navigable (greyed out) — used for temporarily-disabled features. */
  disabled?: boolean;
}

/** Icon for a per-active-strategy sidebar entry (see hooks/useActiveStrategies.ts and
 * components/AppLayout.tsx) — every active strategy gets the same icon regardless of
 * direction or what it displays. */
export const STRATEGY_NAV_ICON = LineChart;

export const NAV_ITEMS: NavItem[] = [
  { path: "/", label: "Dashboard", icon: LayoutDashboard, permission: "view_trading", group: "Trading" },
  { path: "/positions", label: "Positions", icon: Briefcase, permission: "view_trading", group: "Trading" },
  { path: "/orders", label: "Orders", icon: Receipt, permission: "view_trading", group: "Trading" },
  { path: "/manual-trade", label: "Manual Trade", icon: Send, permission: "trade", group: "Trading" },
  { path: "/prices", label: "Prices", icon: CandlestickChart, permission: "view_trading", group: "Trading" },
  {
    path: "/backtesting",
    label: "Backtesting",
    icon: FlaskConical,
    permission: "edit_own_strategies",
    group: "Strategies",
    // Temporarily disabled (see src/api/main.py) — kept visible but not navigable.
    disabled: true,
  },
  {
    path: "/jobs",
    label: "Schedule Jobs",
    icon: Clock,
    permission: "manage_users",
    group: "System",
  },
  { path: "/users", label: "Users", icon: UsersIcon, permission: "manage_users", group: "System" },
  {
    path: "/reports",
    label: "Reports",
    icon: BarChart3,
    permission: "manage_users",
    group: "System",
  },
  { path: "/settings", label: "Settings", icon: SettingsIcon, permission: "change_password", group: "Settings" },
];

/** Ordered group labels for the sidebar; anything not listed falls to the end. */
export const NAV_GROUP_ORDER = ["Trading", "Strategies", "System", "Settings"];

/** Explicit landing route per role (admin has no view_trading, so "/" would 404 for them). */
export function defaultPathFor(role: Role | null): string {
  if (role === "admin") return "/users";
  if (role === "trader" || role === "analyst") return "/";
  return "/settings";
}

