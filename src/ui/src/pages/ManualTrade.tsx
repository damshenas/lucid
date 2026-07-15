import { useEffect, useState } from "react";
import { Send } from "lucide-react";
import { api } from "../api/client";
import { ASSET_CLASSES } from "../lib/assetClasses";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Select } from "../components/ui/Select";
import type { WatchlistItem } from "../types";

const TICKER_DATALIST_ID = "manual-trade-known-tickers";

export function ManualTrade() {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [ticker, setTicker] = useState("");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [quantity, setQuantity] = useState("");
  const [assetClass, setAssetClass] = useState(ASSET_CLASSES[0]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    api.watchlist().then(setWatchlist).catch(() => {});
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const order = await api.placeManualOrder({
        ticker: ticker.trim().toUpperCase(),
        side,
        quantity: Number(quantity),
        asset_class: assetClass,
      });
      setSuccess(
        `${order.side === "buy" ? "Bought" : "Sold"} ${order.quantity} ${order.ticker} @ ${
          order.price ?? "—"
        } (${order.paper ? "paper" : "live"})`,
      );
      setQuantity("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="animate-fade-in-up space-y-4">
      <h2 className="text-xl font-semibold tracking-tight">Manual Trade</h2>

      {error && (
        <p className="rounded-xl border border-rose/30 bg-rose/10 px-3 py-2 text-sm text-rose">
          {error}
        </p>
      )}
      {success && (
        <p className="rounded-xl border border-cyan/30 bg-cyan/10 px-3 py-2 text-sm text-cyan">
          {success}
        </p>
      )}

      <Card>
        <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
          <label className="block">
            <span className="mb-1 block text-xs text-white/40">Ticker</span>
            <input
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              required
              list={TICKER_DATALIST_ID}
              placeholder="AAPL"
              className="w-32 rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-sm uppercase text-white outline-none transition-colors focus:border-violet/50 focus:glow-violet"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-white/40">Side</span>
            <Select value={side} onChange={(e) => setSide(e.target.value as "buy" | "sell")} className="w-28">
              <option value="buy" className="bg-surface">
                Buy
              </option>
              <option value="sell" className="bg-surface">
                Sell
              </option>
            </Select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-white/40">Quantity</span>
            <input
              type="number"
              step="any"
              min="0"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              required
              className="w-32 rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-sm text-white outline-none transition-colors focus:border-violet/50 focus:glow-violet"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-white/40">Asset class</span>
            <Select value={assetClass} onChange={(e) => setAssetClass(e.target.value)} className="w-32">
              {ASSET_CLASSES.map((ac) => (
                <option key={ac} value={ac} className="bg-surface">
                  {ac}
                </option>
              ))}
            </Select>
          </label>
          <Button type="submit" disabled={submitting}>
            <Send size={16} />
            {submitting ? "Placing…" : `Place ${side} order`}
          </Button>
          <Badge tone="neutral">discretionary — bypasses strategy sizing</Badge>
        </form>
      </Card>

      <datalist id={TICKER_DATALIST_ID}>
        {watchlist.map((w) => (
          <option key={w.ticker} value={w.ticker} />
        ))}
      </datalist>
    </div>
  );
}
