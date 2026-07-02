import { Navigate } from "react-router-dom";
import type { ReactNode } from "react";
import { defaultPathFor } from "../lib/nav";
import { hasPermission } from "../lib/permissions";
import type { Permission, Role } from "../lib/permissions";

interface Props {
  role: Role | null;
  permission: Permission;
  children: ReactNode;
}

/**
 * Client-side route gate for nav/UX purposes only. The backend independently
 * verifies and enforces the same permission on every request.
 */
export function RequirePermission({ role, permission, children }: Props) {
  if (!hasPermission(role, permission)) {
    return <Navigate to={defaultPathFor(role)} replace />;
  }
  return <>{children}</>;
}
