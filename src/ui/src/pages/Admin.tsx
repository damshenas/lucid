import { useEffect, useState } from "react";
import { RefreshCw, UserPlus } from "lucide-react";
import { api } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import type { AdminUser, Job } from "../types";

const ROLES = ["viewer", "trader", "admin"];

export function Admin() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("viewer");
  const [creating, setCreating] = useState(false);

  function refresh() {
    api.adminUsers().then(setUsers).catch((e) => setError((e as Error).message));
    api.adminJobs().then(setJobs).catch((e) => setError((e as Error).message));
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
      setRole("viewer");
      refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="animate-fade-in-up space-y-4">
      <h2 className="text-xl font-semibold tracking-tight">Admin</h2>

      {error && (
        <p className="rounded-xl border border-rose/30 bg-rose/10 px-3 py-2 text-sm text-rose">
          {error}
        </p>
      )}

      <Card>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-white/40">
          Users
        </h3>
        <div className="mb-4 overflow-hidden rounded-xl border border-white/5">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-white/10 text-white/40">
              <tr>
                <th className="px-4 py-3 font-medium">Username</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium">Active</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {users.map((u) => (
                <tr key={u.id} className="transition-colors hover:bg-white/5">
                  <td className="px-4 py-3 font-medium">{u.username}</td>
                  <td className="px-4 py-3">
                    <Badge tone="violet">{u.role}</Badge>
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={u.is_active === false ? "rose" : "cyan"}>
                      {u.is_active === false ? "inactive" : "active"}
                    </Badge>
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
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-sm text-white outline-none transition-colors focus:border-violet/50 focus:glow-violet"
            >
              {ROLES.map((r) => (
                <option key={r} value={r} className="bg-surface">
                  {r}
                </option>
              ))}
            </select>
          </label>
          <Button type="submit" disabled={creating}>
            <UserPlus size={16} />
            {creating ? "Creating…" : "Create user"}
          </Button>
        </form>
      </Card>

      <Card>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-white/40">
            Scheduled jobs
          </h3>
          <Button variant="ghost" onClick={refresh}>
            <RefreshCw size={16} />
          </Button>
        </div>
        {jobs.length === 0 ? (
          <p className="py-6 text-center text-sm text-white/40">No jobs reported.</p>
        ) : (
          <div className="overflow-hidden rounded-xl border border-white/5">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-white/10 text-white/40">
                <tr>
                  <th className="px-4 py-3 font-medium">Job</th>
                  <th className="px-4 py-3 font-medium">Last run</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {jobs.map((j) => (
                  <tr key={j.id} className="transition-colors hover:bg-white/5">
                    <td className="px-4 py-3 font-medium">{j.name}</td>
                    <td className="px-4 py-3 text-white/60">{j.last_run ?? "never"}</td>
                    <td className="px-4 py-3">
                      <Badge tone={j.last_status === "error" ? "rose" : "cyan"}>
                        {j.last_status ?? "pending"}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
