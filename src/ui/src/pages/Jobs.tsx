import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import type { Job } from "../types";

export function Jobs() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    api.adminJobs().then(setJobs).catch((e) => setError((e as Error).message));
  }

  useEffect(refresh, []);

  return (
    <div className="animate-fade-in-up space-y-4">
      <h2 className="text-xl font-semibold tracking-tight">Schedule Jobs</h2>

      {error && (
        <p className="rounded-xl border border-rose/30 bg-rose/10 px-3 py-2 text-sm text-rose">
          {error}
        </p>
      )}

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
