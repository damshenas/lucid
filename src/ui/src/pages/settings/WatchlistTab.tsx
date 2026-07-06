import { useEffect, useMemo, useState } from "react";
import { Plus, X } from "lucide-react";
import { api } from "../../api/client";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Select } from "../../components/ui/Select";
import { Tabs, type TabDef } from "../../components/ui/Tabs";
import { useUnsavedChangesGuard } from "../../hooks/useUnsavedChangesGuard";
import { ASSET_CLASSES } from "../../lib/assetClasses";
import { humanize } from "./schemaTree";
import type { WatchlistItem } from "../../types";

type PollInterval = "1m" | "1h";

interface DraftItem {
  ticker: string;
  asset_class: string;
  poll_interval: PollInterval;
}

function toDraft(items: WatchlistItem[]): DraftItem[] {
  return items.map((i) => ({ ticker: i.ticker, asset_class: i.asset_class, poll_interval: i.poll_interval }));
}

/** Only ticker/asset_class/poll_interval participate in the dirty check — `enabled`
 * isn't editable from this UI and `has_bars` can flip in the background (a fetch job
 * completing) with no user action, so including either would show a false "unsaved
 * changes" state. */
function isDirty(saved: DraftItem[], draft: DraftItem[]): boolean {
  if (saved.length !== draft.length) return true;
  const savedByTicker = new Map(saved.map((s) => [s.ticker, s]));
  return draft.some((d) => {
    const s = savedByTicker.get(d.ticker);
    return !s || s.asset_class !== d.asset_class || s.poll_interval !== d.poll_interval;
  });
}

interface Props {
  canManage: boolean;
}

/**
 * Watchlist as a compact chip list (not one row per ticker — see Settings > Price >
 * Watchlist) instead of the old table on the Prices page. Every edit (adding a
 * ticker, removing one, toggling its 1m/1h color) only changes local draft state;
 * nothing reaches the backend until "Save" is clicked (see save() below), and
 * navigating away or closing the tab with unsaved changes prompts for confirmation
 * (useUnsavedChangesGuard).
 */
export function WatchlistTab({ canManage }: Props) {
  const [saved, setSaved] = useState<WatchlistItem[]>([]);
  const [draft, setDraft] = useState<DraftItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedMessage, setSavedMessage] = useState(false);
  const [newTicker, setNewTicker] = useState("");
  const [newAssetClass, setNewAssetClass] = useState(ASSET_CLASSES[0]);
  const [addError, setAddError] = useState<string | null>(null);

  function load() {
    return api
      .watchlist()
      .then((items) => {
        setSaved(items);
        setDraft(toDraft(items));
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoaded(true));
  }

  useEffect(() => {
    load();
  }, []);

  const dirty = useMemo(() => isDirty(toDraft(saved), draft), [saved, draft]);
  useUnsavedChangesGuard(dirty);

  function addTicker(e: React.FormEvent) {
    e.preventDefault();
    const t = newTicker.trim().toUpperCase();
    setAddError(null);
    if (!t) return;
    if (draft.some((d) => d.ticker === t)) {
      setAddError(`${t} is already in the list.`);
      return;
    }
    setDraft((prev) => [...prev, { ticker: t, asset_class: newAssetClass, poll_interval: "1h" }]);
    setNewTicker("");
  }

  function removeTicker(ticker: string) {
    setDraft((prev) => prev.filter((d) => d.ticker !== ticker));
  }

  function toggleInterval(ticker: string) {
    setDraft((prev) =>
      prev.map((d) =>
        d.ticker === ticker ? { ...d, poll_interval: d.poll_interval === "1h" ? "1m" : "1h" } : d,
      ),
    );
  }

  function discard() {
    setDraft(toDraft(saved));
    setAddError(null);
  }

  async function save() {
    setSaving(true);
    setError(null);
    setSavedMessage(false);
    try {
      const savedByTicker = new Map(saved.map((s) => [s.ticker, s]));
      const draftByTicker = new Map(draft.map((d) => [d.ticker, d]));

      const toAdd = draft.filter((d) => !savedByTicker.has(d.ticker));
      const toRemove = saved.filter((s) => !draftByTicker.has(s.ticker));
      const toUpdate = draft.filter((d) => {
        const s = savedByTicker.get(d.ticker);
        return s && s.poll_interval !== d.poll_interval;
      });

      await Promise.all([
        ...toAdd.map((d) => api.addToWatchlist(d.ticker, d.asset_class, d.poll_interval)),
        ...toRemove.map((s) => api.removeFromWatchlist(s.ticker)),
        ...toUpdate.map((d) => api.updateWatchlistItem(d.ticker, { poll_interval: d.poll_interval })),
      ]);

      await load();
      setSavedMessage(true);
    } catch (e) {
      setError((e as Error).message);
      await load(); // resync with whatever actually landed before the failure
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    if (!savedMessage) return;
    const timer = setTimeout(() => setSavedMessage(false), 4000);
    return () => clearTimeout(timer);
  }, [savedMessage]);

  function chipGrid(items: DraftItem[]) {
    if (items.length === 0) {
      return (
        <p className="py-6 text-center text-sm text-white/40">
          No tickers here yet — add one below.
        </p>
      );
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
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-white/40">Watchlist</h3>
          <p className="text-xs text-white/40">
            Click a ticker to switch its price polling between{" "}
            <span className="text-cyan">1-hour (blue)</span> and{" "}
            <span className="text-emerald-400">1-minute (green)</span> — new tickers default to
            1-hour. Changes are local until you press Save.
          </p>
        </div>
        {canManage && (
          <div className="flex items-center gap-2">
            {dirty && (
              <Button variant="ghost" onClick={discard} disabled={saving}>
                Discard
              </Button>
            )}
            <Button onClick={save} disabled={!dirty || saving}>
              {saving ? "Saving…" : dirty ? "Save changes" : "Saved"}
            </Button>
          </div>
        )}
      </div>

      {canManage && (
        <form onSubmit={addTicker} className="flex flex-wrap items-end gap-2">
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
      )}

      {addError && <p className="text-sm text-rose">{addError}</p>}

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
      {savedMessage && (
        <p className="rounded-xl border border-cyan/30 bg-cyan/10 px-3 py-2 text-sm text-cyan">
          Saved.
        </p>
      )}
    </div>
  );
}
