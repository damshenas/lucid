import { useState } from "react";
import { Inbox, RefreshCw, Search } from "lucide-react";
import { api } from "../api/client";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Sparkline } from "../components/ui/Sparkline";
import type { PriceBars } from "../types";

const INTERVALS = ["1d", "15m"];

export function Prices() {
  const [ticker, setTicker] = useState("");
  const [interval, setInterval_] = useState("1d");
  const [data, setData] = useState<PriceBars | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [backfillDays, setBackfillDays] = useState(365);
  const [backfillStatus, setBackfillStatus] = useState<string | null>(null);
  const [backfilling, setBackfilling] = useState(false);

  async function fetchBars() {
    if (!ticker.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setData(await api.priceBars(ticker.trim().toUpperCase(), interval, 250));
    } catch (e) {
      setData(null);
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function backfill() {
    if (!ticker.trim()) return;
    setBackfilling(true);
    setBackfillStatus(null);
    setError(null);
    try {
      const result = await api.backfillPrices(ticker.trim().toUpperCase(), backfillDays);
      setBackfillStatus(`Backfilled ${result.rows} rows.`);
      await fetchBars();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBackfilling(false);
    }
  }

  const bars = data?.bars ?? [];
  const last = bars.at(-1);
  const first = bars[0];
  const change =
    last && first && first.close ? ((last.close - first.close) / first.close) * 100 : null;
  const recent = bars.slice(-50).reverse();

  return (
    <div className="animate-fade-in-up space-y-4">
      <h2 className="text-xl font-semibold tracking-tight">Prices</h2>

      <Card className="flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="mb-1 block text-xs text-white/40">Ticker</span>
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && fetchBars()}
            placeholder="AAPL"
            className="w-32 rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-sm uppercase text-white outline-none transition-colors focus:border-violet/50 focus:glow-violet"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-white/40">Interval</span>
          <select
            value={interval}
            onChange={(e) => setInterval_(e.target.value)}
            className="rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-sm text-white outline-none transition-colors focus:border-violet/50 focus:glow-violet"
          >
            {INTERVALS.map((i) => (
              <option key={i} value={i} className="bg-surface">
                {i}
              </option>
            ))}
          </select>
        </label>
        <Button onClick={fetchBars} disabled={loading || !ticker.trim()}>
          <Search size={16} />
          {loading ? "Loading…" : "Load"}
        </Button>

        <div className="ml-auto flex items-end gap-2">
          <label className="block">
            <span className="mb-1 block text-xs text-white/40">Backfill days</span>
            <input
              type="number"
              value={backfillDays}
              onChange={(e) => setBackfillDays(parseInt(e.target.value, 10) || 365)}
              className="w-24 rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-sm text-white outline-none transition-colors focus:border-violet/50 focus:glow-violet"
            />
          </label>
          <Button variant="secondary" onClick={backfill} disabled={backfilling || !ticker.trim()}>
            <RefreshCw size={16} className={backfilling ? "animate-spin" : ""} />
            Backfill
          </Button>
        </div>
      </Card>

      {error && (
        <p className="rounded-xl border border-rose/30 bg-rose/10 px-3 py-2 text-sm text-rose">
          {error}
        </p>
      )}
      {backfillStatus && (
        <p className="rounded-xl border border-cyan/30 bg-cyan/10 px-3 py-2 text-sm text-cyan">
          {backfillStatus}
        </p>
      )}

      {!data ? (
        <Card className="flex flex-col items-center gap-2 py-10 text-center text-white/50">
          <Inbox size={28} className="text-white/30" />
          <p className="text-sm">Enter a ticker and press Load.</p>
        </Card>
      ) : (
        <>
          <Card>
            <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
              <Stat label="Last" value={last?.close.toFixed(2) ?? "—"} />
              <Stat label="Open" value={last?.open.toFixed(2) ?? "—"} />
              <Stat label="High" value={last?.high.toFixed(2) ?? "—"} />
              <Stat label="Low" value={last?.low.toFixed(2) ?? "—"} />
              <Stat
                label="Change"
                value={change === null ? "—" : `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`}
                tone={change === null ? undefined : change >= 0 ? "cyan" : "rose"}
              />
              <Stat label="Bars" value={String(bars.length)} />
              <Stat label="Latest" value={last?.date.slice(0, 10) ?? "—"} />
            </div>
            <Sparkline
              values={bars.map((b) => b.close)}
              className="h-16 w-full"
              stroke="#7c3aed"
            />
          </Card>

          <Card className="overflow-hidden !p-0">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-white/10 text-white/40">
                <tr>
                  <th className="px-4 py-3 font-medium">Date</th>
                  <th className="px-4 py-3 font-medium">Open</th>
                  <th className="px-4 py-3 font-medium">High</th>
                  <th className="px-4 py-3 font-medium">Low</th>
                  <th className="px-4 py-3 font-medium">Close</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {recent.map((b) => (
                  <tr key={b.date} className="transition-colors hover:bg-white/5">
                    <td className="px-4 py-3 font-medium">{b.date.slice(0, 10)}</td>
                    <td className="px-4 py-3">{b.open.toFixed(2)}</td>
                    <td className="px-4 py-3">{b.high.toFixed(2)}</td>
                    <td className="px-4 py-3">{b.low.toFixed(2)}</td>
                    <td className="px-4 py-3">{b.close.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "cyan" | "rose";
}) {
  return (
    <div>
      <p className="text-xs text-white/40">{label}</p>
      <p
        className={`text-sm font-semibold ${
          tone === "cyan" ? "text-cyan" : tone === "rose" ? "text-rose" : "text-white"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
