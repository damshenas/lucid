import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { WatchlistItem } from "../types";

export type PollInterval = "1m" | "1h";
export type Region = "us" | "eu" | "em";

export interface WatchlistDraftItem {
  ticker: string;
  asset_class: string;
  poll_interval: PollInterval;
  region: Region;
}

function toDraft(items: WatchlistItem[]): WatchlistDraftItem[] {
  // Only real watchlist rows (on_watchlist=true) ever become draft items — a
  // disk-only "ghost" entry (bars fetched ad-hoc, never actually added — see
  // GET /api/v1/prices/watchlist) must never be treated as pre-existing, or
  // "saving" a toggle on it 404s (PATCH/DELETE on a ticker never really added).
  return items
    .filter((i) => i.on_watchlist)
    .map((i) => ({
      ticker: i.ticker,
      asset_class: i.asset_class,
      poll_interval: i.poll_interval,
      region: i.region,
    }));
}

function isDirty(saved: WatchlistDraftItem[], draft: WatchlistDraftItem[]): boolean {
  if (saved.length !== draft.length) return true;
  const savedByTicker = new Map(saved.map((s) => [s.ticker, s]));
  return draft.some((d) => {
    const s = savedByTicker.get(d.ticker);
    return (
      !s ||
      s.asset_class !== d.asset_class ||
      s.poll_interval !== d.poll_interval ||
      s.region !== d.region
    );
  });
}

export interface WatchlistDraft {
  draft: WatchlistDraftItem[];
  loaded: boolean;
  error: string | null;
  dirty: boolean;
  /** Returns an error message on failure (duplicate ticker), or null on success. */
  addTicker: (ticker: string, assetClass: string) => string | null;
  removeTicker: (ticker: string) => void;
  toggleInterval: (ticker: string) => void;
  cycleRegion: (ticker: string) => void;
  /** Diffs draft against last-saved and issues the minimal add/remove/update calls,
   * then refetches. Called from the page-level Save button (pages/Settings.tsx),
   * alongside the schema-field save — there's no separate Watchlist save button. */
  commit: () => Promise<void>;
}

/**
 * Local "draft" state for the Settings > Price > Watchlist chip list (see
 * pages/settings/WatchlistTab.tsx). Add/remove/toggle-color only ever change this
 * draft; nothing reaches the backend until commit(). Lifted into its own hook (rather
 * than owned by the tab component) so the single page-level Save button in
 * pages/Settings.tsx can drive it together with the schema-field save — there is
 * intentionally no separate Watchlist-only save/discard button.
 */
export function useWatchlistDraft(): WatchlistDraft {
  const [saved, setSaved] = useState<WatchlistDraftItem[]>([]);
  const [draft, setDraft] = useState<WatchlistDraftItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function load() {
    return api
      .watchlist()
      .then((items) => {
        const normalized = toDraft(items);
        setSaved(normalized);
        setDraft(normalized);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoaded(true));
  }

  useEffect(() => {
    load();
  }, []);

  const dirty = useMemo(() => isDirty(saved, draft), [saved, draft]);

  function addTicker(ticker: string, assetClass: string): string | null {
    const t = ticker.trim().toUpperCase();
    if (!t) return null;
    if (draft.some((d) => d.ticker === t)) return `${t} is already in the list.`;
    setDraft((prev) => [
      ...prev,
      { ticker: t, asset_class: assetClass, poll_interval: "1h", region: "us" },
    ]);
    return null;
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

  const REGION_CYCLE: Region[] = ["us", "eu", "em"];

  function cycleRegion(ticker: string) {
    setDraft((prev) =>
      prev.map((d) => {
        if (d.ticker !== ticker) return d;
        const next = REGION_CYCLE[(REGION_CYCLE.indexOf(d.region) + 1) % REGION_CYCLE.length];
        return { ...d, region: next };
      }),
    );
  }

  async function commit(): Promise<void> {
    const savedByTicker = new Map(saved.map((s) => [s.ticker, s]));
    const draftByTicker = new Map(draft.map((d) => [d.ticker, d]));

    const toAdd = draft.filter((d) => !savedByTicker.has(d.ticker));
    const toRemove = saved.filter((s) => !draftByTicker.has(s.ticker));
    const toUpdate = draft.filter((d) => {
      const s = savedByTicker.get(d.ticker);
      return s !== undefined && (s.poll_interval !== d.poll_interval || s.region !== d.region);
    });

    // Each op is tracked with the ticker it belongs to and run independently
    // (allSettled, not all) — one failing must not hide whether the others
    // actually landed, and the caller needs to know exactly which ticker(s)
    // failed so their attempted change can be preserved rather than silently
    // discarded by the reload below (bugs.md finding 19).
    const ops: { ticker: string; run: () => Promise<unknown> }[] = [
      ...toAdd.map((d) => ({
        ticker: d.ticker,
        run: () => api.addToWatchlist(d.ticker, d.asset_class, d.poll_interval, d.region),
      })),
      ...toRemove.map((s) => ({ ticker: s.ticker, run: () => api.removeFromWatchlist(s.ticker) })),
      ...toUpdate.map((d) => ({
        ticker: d.ticker,
        run: () =>
          api.updateWatchlistItem(d.ticker, { poll_interval: d.poll_interval, region: d.region }),
      })),
    ];

    const results = await Promise.allSettled(ops.map((op) => op.run()));
    const failedTickers = new Set<string>();
    const errors: string[] = [];
    results.forEach((result, i) => {
      if (result.status === "rejected") {
        failedTickers.add(ops[i].ticker);
        errors.push(`${ops[i].ticker}: ${(result.reason as Error).message}`);
      }
    });

    // Resync with whatever actually landed server-side, but keep the user's
    // still-unsaved edit for any ticker whose operation failed instead of
    // wiping it out from under them — they'd otherwise have to redo it from
    // scratch with no indication anything went wrong for that specific ticker.
    const preserved = draft.filter((d) => failedTickers.has(d.ticker));
    try {
      const items = await api.watchlist();
      const normalized = toDraft(items);
      setSaved(normalized);
      const preservedTickers = new Set(preserved.map((p) => p.ticker));
      const merged = normalized.filter((n) => !preservedTickers.has(n.ticker));
      setDraft([...merged, ...preserved]);
    } catch (e) {
      setError((e as Error).message);
    }

    if (errors.length > 0) {
      throw new Error(`some watchlist changes failed to save — ${errors.join("; ")}`);
    }
  }

  return { draft, loaded, error, dirty, addTicker, removeTicker, toggleInterval, cycleRegion, commit };
}
