import { useEffect, useState } from "react";
import { KeyRound, Power, RotateCcw, Trash2, UserPlus } from "lucide-react";
import { api } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Select } from "../components/ui/Select";
import type { AdminUser } from "../types";

const ROLES = ["analyst", "trader", "admin"];

export function Users() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("analyst");
  const [creating, setCreating] = useState(false);

  function refresh() {
    api.adminUsers().then(setUsers).catch((e) => setError((e as Error).message));
  }

  useEffect(refresh, []);

  async function createUser(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      await api.createAdminUser(username, password, role);
      setUsername("");
      setPassword("");
      setRole("analyst");
      refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCreating(false);
    }
  }

  async function changeRole(u: AdminUser, newRole: string) {
    setBusyId(u.id);
    setError(null);
    try {
      await api.updateAdminUser(u.id, { role: newRole });
      refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  async function toggleActive(u: AdminUser) {
    setBusyId(u.id);
    setError(null);
    try {
      await api.updateAdminUser(u.id, { is_active: u.is_active === false });
      refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  async function resetPassword(u: AdminUser) {
    const newPassword = window.prompt(`New password for "${u.username}" (min 8 chars):`);
    if (!newPassword) return;
    setBusyId(u.id);
    setError(null);
    try {
      await api.resetUserPassword(u.id, newPassword);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  async function deleteUser(u: AdminUser) {
    if (!window.confirm(`Delete user "${u.username}"? This cannot be undone.`)) return;
    setBusyId(u.id);
    setError(null);
    try {
      await api.deleteAdminUser(u.id);
      refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  async function resetTradingData(u: AdminUser) {
    if (
      !window.confirm(
        `Reset ALL trading data for "${u.username}" — positions, orders, signals, and ` +
          `the strategy decision log? This cannot be undone. Their broker's current ` +
          `holdings will be re-synced into positions right after.`
      )
    )
      return;
    setBusyId(u.id);
    setError(null);
    try {
      const result = await api.resetTradingData(u.id, true);
      const perAssetClass = result.synced[u.username] ?? {};
      const errors = Object.entries(perAssetClass)
        .filter(([, r]) => r.error)
        .map(([assetClass, r]) => `${assetClass}: ${r.error}`);
      if (errors.length > 0) {
        setError(`Reset done, but broker sync failed for some asset classes — ${errors.join("; ")}`);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="animate-fade-in-up space-y-4">
      <h2 className="text-xl font-semibold tracking-tight">Users</h2>

      {error && (
        <p className="rounded-xl border border-rose/30 bg-rose/10 px-3 py-2 text-sm text-rose">
          {error}
        </p>
      )}

      <Card>
        <div className="mb-4 overflow-hidden rounded-xl border border-white/5">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-white/10 text-white/40">
              <tr>
                <th className="px-4 py-3 font-medium">Username</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium">Active</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {users.map((u) => (
                <tr key={u.id} className="transition-colors hover:bg-white/5">
                  <td className="px-4 py-3 font-medium">{u.username}</td>
                  <td className="px-4 py-3">
                    <Select
                      value={u.role}
                      disabled={busyId === u.id}
                      onChange={(e) => changeRole(u, e.target.value)}
                      className="w-28"
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r} className="bg-surface">
                          {r}
                        </option>
                      ))}
                    </Select>
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={u.is_active === false ? "rose" : "cyan"}>
                      {u.is_active === false ? "inactive" : "active"}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Button
                        variant="ghost"
                        disabled={busyId === u.id}
                        onClick={() => resetPassword(u)}
                        title="Reset password"
                      >
                        <KeyRound size={16} />
                      </Button>
                      <Button
                        variant="ghost"
                        disabled={busyId === u.id}
                        onClick={() => toggleActive(u)}
                        title={u.is_active === false ? "Activate" : "Deactivate"}
                      >
                        <Power size={16} />
                      </Button>
                      {u.role === "trader" && (
                        <Button
                          variant="ghost"
                          disabled={busyId === u.id}
                          onClick={() => resetTradingData(u)}
                          title="Reset trading data (positions/orders/signals/decisions) and re-sync from broker"
                        >
                          <RotateCcw size={16} />
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        disabled={busyId === u.id}
                        onClick={() => deleteUser(u)}
                        title="Delete user"
                      >
                        <Trash2 size={16} />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <form onSubmit={createUser} className="flex flex-wrap items-end gap-3">
          <label className="block">
            <span className="mb-1 block text-xs text-white/40">Username</span>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              className="w-40 rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-sm text-white outline-none transition-colors focus:border-violet/50 focus:glow-violet"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-white/40">Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              className="w-40 rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-sm text-white outline-none transition-colors focus:border-violet/50 focus:glow-violet"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-white/40">Role</span>
            <Select value={role} onChange={(e) => setRole(e.target.value)} className="w-32">
              {ROLES.map((r) => (
                <option key={r} value={r} className="bg-surface">
                  {r}
                </option>
              ))}
            </Select>
          </label>
          <Button type="submit" disabled={creating}>
            <UserPlus size={16} />
            {creating ? "Creating…" : "Create user"}
          </Button>
        </form>
      </Card>
    </div>
  );
}

