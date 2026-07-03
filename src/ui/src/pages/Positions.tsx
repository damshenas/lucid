import { useEffect, useState } from "react";
import { Inbox, RefreshCw } from "lucide-react";
import { api } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Select } from "../components/ui/Select";
import type { Position } from "../types";

// Mirrors AssetClass in src/conf/schema.py — kept as a fixed list (like
// pages/Backtesting.tsx's INTERVALS) so the sync target is always one of the
// backend's known values rather than free text.
const ASSET_CLASSES = ["equity", "commodity", "crypto", "fx"];

export function Positions() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [assetClass, setAssetClass] = useState(ASSET_CLASSES[0]);
  const [error, setError] = useState<string | null>(null);
  const [syncStatus, setSyncStatus] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  function refresh() {
    api.positions().then(setPositions).catch((e) => setError((e as Error).message));
  }

  useEffect(refresh, []);

  async function sync() {
    setSyncing(true);
    setError(null);
    setSyncStatus(null);
    try {
      const result = await api.syncPositions(assetClass);
      setSyncStatus(`Synced ${result.synced}, closed ${result.closed}.`);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div className="animate-fade-in-up space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold tracking-tight">Positions</h2>
        <div className="flex items-center gap-2">
          <Select
            value={assetClass}
            onChange={(e) => setAssetClass(e.target.value)}
            className="w-32"
          >
            {ASSET_CLASSES.map((ac) => (
              <option key={ac} value={ac} className="bg-surface">
                {ac}
              </option>
            ))}
          </Select>
          <Button variant="secondary" onClick={sync} disabled={syncing}>
            <RefreshCw size={16} className={syncing ? "animate-spin" : ""} />
            Sync
          </Button>
        </div>
      </div>

      {error && (
        <p className="rounded-xl border border-rose/30 bg-rose/10 px-3 py-2 text-sm text-rose">
          {error}
        </p>
      )}
      {syncStatus && (
        <p className="rounded-xl border border-cyan/30 bg-cyan/10 px-3 py-2 text-sm text-cyan">
          {syncStatus}
        </p>
      )}

      {positions.length === 0 ? (
        <Card className="flex flex-col items-center gap-2 py-10 text-center text-white/50">
          <Inbox size={28} className="text-white/30" />
          <p className="text-sm">No open positions.</p>
        </Card>
      ) : (
        <>
          {/* Mobile: stacked cards */}
          <div className="space-y-3 sm:hidden">
            {positions.map((p) => (
              <Card key={p.ticker}>
                <div className="flex items-center justify-between">
                  <span className="font-semibold">{p.ticker}</span>
                  <Badge tone="cyan">{p.asset_class}</Badge>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <p className="text-white/40">Quantity</p>
                    <p className="font-medium">{p.quantity}</p>
                  </div>
                  <div>
                    <p className="text-white/40">Avg price</p>
                    <p className="font-medium">{p.avg_price}</p>
                  </div>
                </div>
              </Card>
            ))}
          </div>

          {/* Desktop/tablet: table */}
          <Card className="hidden overflow-hidden !p-0 sm:block">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-white/10 text-white/40">
                <tr>
                  <th className="px-4 py-3 font-medium">Ticker</th>
                  <th className="px-4 py-3 font-medium">Qty</th>
                  <th className="px-4 py-3 font-medium">Avg price</th>
                  <th className="px-4 py-3 font-medium">Class</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {positions.map((p) => (
                  <tr key={p.ticker} className="transition-colors hover:bg-white/5">
                    <td className="px-4 py-3 font-medium">{p.ticker}</td>
                    <td className="px-4 py-3">{p.quantity}</td>
                    <td className="px-4 py-3">{p.avg_price}</td>
                    <td className="px-4 py-3">
                      <Badge tone="cyan">{p.asset_class}</Badge>
                    </td>
                    <td className="px-4 py-3 text-white/50">{p.status}</td>
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
