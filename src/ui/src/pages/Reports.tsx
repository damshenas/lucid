import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Select } from "../components/ui/Select";
import type { FetchActivityRow, PriceCoverageRow } from "../types";

type Tab = "coverage" | "activity";

export function Reports() {
  const [tab, setTab] = useState<Tab>("coverage");
  const [coverage, setCoverage] = useState<PriceCoverageRow[]>([]);
  const [activity, setActivity] = useState<FetchActivityRow[]>([]);
  const [days, setDays] = useState(7);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    setError(null);
    api.priceCoverageReport().then(setCoverage).catch((e) => setError((e as Error).message));
    api
      .fetchActivityReport(days)
      .then(setActivity)
      .catch((e) => setError((e as Error).message));
  }

  useEffect(refresh, [days]);

  return (
    <div className="animate-fade-in-up space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold tracking-tight">Reports</h2>
        <Button variant="ghost" onClick={refresh}>
          <RefreshCw size={16} />
        </Button>
      </div>

      {error && (
        <p className="rounded-xl border border-rose/30 bg-rose/10 px-3 py-2 text-sm text-rose">
          {error}
        </p>
      )}

      <div className="flex gap-2">
        <Button variant={tab === "coverage" ? "secondary" : "ghost"} onClick={() => setTab("coverage")}>
          Price coverage
        </Button>
        <Button variant={tab === "activity" ? "secondary" : "ghost"} onClick={() => setTab("activity")}>
          Fetch activity
        </Button>
      </div>

      {tab === "coverage" && (
        <Card className="overflow-hidden !p-0">
          {coverage.length === 0 ? (
            <p className="py-6 text-center text-sm text-white/40">No stored price bars yet.</p>
          ) : (
            <table className="w-full text-left text-sm">
              <thead className="border-b border-white/10 text-white/40">
                <tr>
                  <th className="px-4 py-3 font-medium">Ticker</th>
                  <th className="px-4 py-3 font-medium">Interval</th>
                  <th className="px-4 py-3 font-medium">Earliest</th>
                  <th className="px-4 py-3 font-medium">Latest</th>
                  <th className="px-4 py-3 font-medium">Bars</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {coverage.map((r) => (
                  <tr key={`${r.ticker}-${r.interval}`} className="transition-colors hover:bg-white/5">
                    <td className="px-4 py-3 font-medium">{r.ticker}</td>
                    <td className="px-4 py-3">
                      <Badge tone="neutral">{r.interval}</Badge>
                    </td>
                    <td className="px-4 py-3 text-white/60">{r.earliest}</td>
                    <td className="px-4 py-3 text-white/60">{r.latest}</td>
                    <td className="px-4 py-3">{r.bar_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      )}

      {tab === "activity" && (
        <div className="space-y-3">
          <label className="inline-block">
            <span className="mb-1 block text-xs text-white/40">Last</span>
            <Select value={String(days)} onChange={(e) => setDays(Number(e.target.value))} className="w-32">
              {[1, 3, 7, 14, 30].map((d) => (
                <option key={d} value={d} className="bg-surface">
                  {d} days
                </option>
              ))}
            </Select>
          </label>
          <Card className="overflow-hidden !p-0">
            {activity.length === 0 ? (
              <p className="py-6 text-center text-sm text-white/40">No fetch attempts recorded.</p>
            ) : (
              <table className="w-full text-left text-sm">
                <thead className="border-b border-white/10 text-white/40">
                  <tr>
                    <th className="px-4 py-3 font-medium">Ticker</th>
                    <th className="px-4 py-3 font-medium">Interval</th>
                    <th className="px-4 py-3 font-medium">When</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 font-medium">Duration</th>
                    <th className="px-4 py-3 font-medium">Rows</th>
                    <th className="px-4 py-3 font-medium">Error</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {activity.map((a, i) => (
                    <tr key={`${a.ticker}-${a.attempted_at}-${i}`} className="transition-colors hover:bg-white/5">
                      <td className="px-4 py-3 font-medium">{a.ticker}</td>
                      <td className="px-4 py-3">
                        <Badge tone="neutral">{a.interval}</Badge>
                      </td>
                      <td className="px-4 py-3 text-white/60">{a.attempted_at ?? "—"}</td>
                      <td className="px-4 py-3">
                        <Badge tone={a.status === "error" ? "rose" : "cyan"}>{a.status}</Badge>
                      </td>
                      <td className="px-4 py-3 text-white/60">{a.duration_seconds.toFixed(2)}s</td>
                      <td className="px-4 py-3">{a.rows_fetched}</td>
                      <td className="px-4 py-3 text-white/40">{a.error_message ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
