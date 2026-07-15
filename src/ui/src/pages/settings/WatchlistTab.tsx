import { useState } from "react";
import { Plus, X } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Select } from "../../components/ui/Select";
import { Tabs, type TabDef } from "../../components/ui/Tabs";
import type { WatchlistDraft, WatchlistDraftItem } from "../../hooks/useWatchlistDraft";
import { ASSET_CLASSES } from "../../lib/assetClasses";
import { humanize } from "./schemaTree";

interface Props {
  watchlist: WatchlistDraft;
  canManage: boolean;
}

/**
 * Watchlist as a compact chip list (not one row per ticker) with an asset-class
 * filter. Purely presentational — all state lives in useWatchlistDraft (see
 * pages/Settings.tsx), whose commit() is wired to the single page-level Save button
 * alongside the schema-field save. There is no Watchlist-only save/discard button
 * here: click a chip again (or remove it) to undo a local change before saving.
 */
export function WatchlistTab({ watchlist, canManage }: Props) {
  const { draft, loaded, error, addTicker, removeTicker, toggleInterval, cycleRegion } = watchlist;
  const [newTicker, setNewTicker] = useState("");
  const [newAssetClass, setNewAssetClass] = useState(ASSET_CLASSES[0]);
  const [addError, setAddError] = useState<string | null>(null);

  function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const err = addTicker(newTicker, newAssetClass);
    setAddError(err);
    if (!err) setNewTicker("");
  }

  function chipGrid(items: WatchlistDraftItem[]) {
    if (items.length === 0) {
      return <p className="py-6 text-center text-sm text-white/40">No tickers here yet.</p>;
    }
    return (
      <div className="flex flex-wrap gap-2">
        {items.map((item) => {
          const isMinute = item.poll_interval === "1m";
          return (
            <span
              key={item.ticker}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
                isMinute
                  ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-400"
                  : "border-cyan/40 bg-cyan/15 text-cyan"
              }`}
            >
              <button
                type="button"
                onClick={() => canManage && toggleInterval(item.ticker)}
                disabled={!canManage}
                title={
                  isMinute
                    ? "1-minute prices — click for 1-hour"
                    : "1-hour prices — click for 1-minute"
                }
                className="disabled:cursor-default"
              >
                {item.ticker}
              </button>
              <button
                type="button"
                onClick={() => canManage && cycleRegion(item.ticker)}
                disabled={!canManage}
                title={`Market-hours region: ${item.region.toUpperCase()} — click to cycle`}
                className="rounded-full bg-black/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-current/70 disabled:cursor-default"
              >
                {item.region}
              </button>
              {canManage && (
                <button
                  type="button"
                  onClick={() => removeTicker(item.ticker)}
                  aria-label={`Remove ${item.ticker}`}
                  className="text-current/60 transition-colors hover:text-rose"
                >
                  <X size={12} />
                </button>
              )}
            </span>
          );
        })}
      </div>
    );
  }

  const filterTabs: TabDef[] = [
    { id: "all", label: "All", content: chipGrid(draft) },
    ...ASSET_CLASSES.map((ac) => ({
      id: ac,
      label: humanize(ac),
      content: chipGrid(draft.filter((d) => d.asset_class === ac)),
    })),
  ];

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-white/40">Watchlist</h3>
        <p className="text-xs text-white/40">
          Click a ticker to switch its price polling between{" "}
          <span className="text-cyan">1-hour (blue)</span> and{" "}
          <span className="text-emerald-400">1-minute (green)</span> — new tickers default to
          1-hour. Click the small region badge to cycle its market-hours gating between
          US / EU / EM. Changes here are local until you press the Save button below.
        </p>
      </div>

      {canManage && (
        <>
          <form onSubmit={handleAdd} className="flex flex-wrap items-end gap-2">
            <label className="block">
              <span className="mb-1 block text-xs text-white/40">Add ticker</span>
              <input
                value={newTicker}
                onChange={(e) => setNewTicker(e.target.value)}
                placeholder="AMZN"
                className="w-28 rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-sm uppercase text-white outline-none transition-colors focus:border-violet/50 focus:glow-violet"
              />
            </label>
            <Select value={newAssetClass} onChange={(e) => setNewAssetClass(e.target.value)} className="w-32">
              {ASSET_CLASSES.map((ac) => (
                <option key={ac} value={ac} className="bg-surface">
                  {humanize(ac)}
                </option>
              ))}
            </Select>
            <Button type="submit" variant="secondary" disabled={!newTicker.trim()}>
              <Plus size={16} />
              Add
            </Button>
          </form>
          {addError && <p className="text-sm text-rose">{addError}</p>}
          <hr className="border-white/10" />
        </>
      )}

      {!loaded ? (
        <p className="py-6 text-center text-sm text-white/40">Loading…</p>
      ) : (
        <Card>
          <Tabs level="nested" tabs={filterTabs} />
        </Card>
      )}

      {error && (
        <p className="rounded-xl border border-rose/30 bg-rose/10 px-3 py-2 text-sm text-rose">
          {error}
        </p>
      )}
    </div>
  );
}
