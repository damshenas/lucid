import { useEffect, useState } from "react";
import { Inbox, Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import { api } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Select } from "../components/ui/Select";
import { Sparkline } from "../components/ui/Sparkline";
import { Toggle } from "../components/ui/Toggle";
import { useAuth } from "../hooks/useAuth";
import { ASSET_CLASSES } from "../lib/assetClasses";
import { hasPermission } from "../lib/permissions";
import type { PriceBars, WatchlistItem } from "../types";

const INTERVALS = ["1d", "15m"];
const TICKER_DATALIST_ID = "known-tickers";

export function Prices() {
  const { role } = useAuth();
  const canManageWatchlist = hasPermission(role, "edit_own_strategies");
  const [ticker, setTicker] = useState("");
  const [interval, setInterval_] = useState("1d");
  const [data, setData] = useState<PriceBars | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [backfillDays, setBackfillDays] = useState(365);
  const [backfillStatus, setBackfillStatus] = useState<string | null>(null);
  const [backfilling, setBackfilling] = useState(false);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [newTicker, setNewTicker] = useState("");
  const [newAssetClass, setNewAssetClass] = useState(ASSET_CLASSES[0]);
  const [watchlistBusy, setWatchlistBusy] = useState<string | null>(null);

  function refreshWatchlist() {
    api
      .watchlist()
      .then(setWatchlist)
      .catch((e) => setError((e as Error).message));
  }

  useEffect(refreshWatchlist, []);

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
      refreshWatchlist();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBackfilling(false);
    }
  }

  async function addTicker(e: React.FormEvent) {
    e.preventDefault();
    const t = newTicker.trim().toUpperCase();
    if (!t) return;
    setWatchlistBusy(t);
    setError(null);
    try {
      await api.addToWatchlist(t, newAssetClass);
      // Fetch bars right away so the strategy scheduler doesn't have to wait for the
      // next daily/intraday price job before this ticker can produce a signal.
      await api.backfillPrices(t, backfillDays).catch(() => {});
      setNewTicker("");
      refreshWatchlist();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setWatchlistBusy(null);
    }
  }

  async function toggleWatchlist(item: WatchlistItem) {
    setWatchlistBusy(item.ticker);
    setError(null);
    try {
      await api.setWatchlistEnabled(item.ticker, !item.enabled);
      refreshWatchlist();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setWatchlistBusy(null);
    }
  }

  async function removeTicker(item: WatchlistItem) {
    setWatchlistBusy(item.ticker);
    setError(null);
    try {
      await api.removeFromWatchlist(item.ticker);
      refreshWatchlist();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setWatchlistBusy(null);
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
            list={TICKER_DATALIST_ID}
            className="w-32 rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-sm uppercase text-white outline-none transition-colors focus:border-violet/50 focus:glow-violet"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-white/40">Interval</span>
          <Select value={interval} onChange={(e) => setInterval_(e.target.value)} className="w-28">
            {INTERVALS.map((i) => (
              <option key={i} value={i} className="bg-surface">
                {i}
              </option>
            ))}
          </Select>
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

      {/* Known tickers (watchlist + anything already backfilled) power the
          autocomplete above via the browser's native datalist. */}
      <datalist id={TICKER_DATALIST_ID}>
        {watchlist.map((w) => (
          <option key={w.ticker} value={w.ticker} />
        ))}
      </datalist>

      <Card className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-white/40">Watchlist</h3>
          <span className="text-xs text-white/40">
            Only enabled tickers here are evaluated by active strategies and kept priced.
          </span>
        </div>

        {canManageWatchlist && (
          <form onSubmit={addTicker} className="flex flex-wrap items-end gap-2">
            <label className="block">
              <span className="mb-1 block text-xs text-white/40">Add ticker</span>
              <input
                value={newTicker}
                onChange={(e) => setNewTicker(e.target.value)}
                placeholder="AMZN"
                list={TICKER_DATALIST_ID}
                className="w-28 rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-sm uppercase text-white outline-none transition-colors focus:border-violet/50 focus:glow-violet"
              />
            </label>
            <Select
              value={newAssetClass}
              onChange={(e) => setNewAssetClass(e.target.value)}
              className="w-32"
            >
              {ASSET_CLASSES.map((ac) => (
                <option key={ac} value={ac} className="bg-surface">
                  {ac}
                </option>
              ))}
            </Select>
            <Button type="submit" variant="secondary" disabled={!newTicker.trim() || watchlistBusy !== null}>
              <Plus size={16} />
              Add
            </Button>
          </form>
        )}

        {watchlist.length === 0 ? (
          <p className="py-6 text-center text-sm text-white/40">
            No tickers yet — add one above to start pricing and evaluating it.
          </p>
        ) : (
          <div className="space-y-2">
            {watchlist.map((w) => (
              <div
                key={w.ticker}
                className="flex items-center justify-between gap-3 rounded-xl border border-white/5 bg-white/5 px-3 py-2"
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{w.ticker}</span>
                  <Badge tone="neutral">{w.asset_class}</Badge>
                  {!w.has_bars && <Badge tone="rose">no bars yet</Badge>}
                </div>
                {canManageWatchlist && (
                  <div className="flex items-center gap-3">
                    <Toggle
                      checked={w.enabled}
                      onChange={() => toggleWatchlist(w)}
                      disabled={watchlistBusy === w.ticker}
                      label={`${w.enabled ? "Disable" : "Enable"} ${w.ticker}`}
                    />
                    <button
                      onClick={() => removeTicker(w)}
                      disabled={watchlistBusy === w.ticker}
                      aria-label={`Remove ${w.ticker}`}
                      className="text-white/40 transition-colors hover:text-rose disabled:opacity-50"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
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
