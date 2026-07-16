export type Role = "admin" | "trader" | "analyst";

export type Permission =
  | "trade"
  | "view_trading"
  | "manage_users"
  | "edit_system_settings"
  | "edit_own_credentials"
  | "edit_own_strategies"
  | "change_password"
  | "manage_trading_data";

/**
 * Mirrors ROLE_PERMISSIONS in src/modules/authorization/__init__.py.
 * Used for client-side nav gating only — the backend independently enforces
 * every permission on every request.
 */
const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  admin: ["manage_users", "edit_system_settings", "change_password", "manage_trading_data"],
  trader: [
    "trade",
    "view_trading",
    "edit_own_credentials",
    "edit_own_strategies",
    "change_password",
  ],
  analyst: ["view_trading", "edit_own_strategies", "change_password"],
};

export function hasPermission(role: Role | null | undefined, permission: Permission): boolean {
  if (!role) return false;
  return ROLE_PERMISSIONS[role]?.includes(permission) ?? false;
}
