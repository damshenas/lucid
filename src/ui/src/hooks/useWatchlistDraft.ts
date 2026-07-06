import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { WatchlistItem } from "../types";

export type PollInterval = "1m" | "1h";

export interface WatchlistDraftItem {
  ticker: string;
  asset_class: string;
  poll_interval: PollInterval;
}

function toDraft(items: WatchlistItem[]): WatchlistDraftItem[] {
  // Only real watchlist rows (on_watchlist=true) ever become draft items — a
  // disk-only "ghost" entry (bars fetched ad-hoc, never actually added — see
  // GET /api/v1/prices/watchlist) must never be treated as pre-existing, or
  // "saving" a toggle on it 404s (PATCH/DELETE on a ticker never really added).
  return items
    .filter((i) => i.on_watchlist)
    .map((i) => ({ ticker: i.ticker, asset_class: i.asset_class, poll_interval: i.poll_interval }));
}

function isDirty(saved: WatchlistDraftItem[], draft: WatchlistDraftItem[]): boolean {
  if (saved.length !== draft.length) return true;
  const savedByTicker = new Map(saved.map((s) => [s.ticker, s]));
  return draft.some((d) => {
    const s = savedByTicker.get(d.ticker);
    return !s || s.asset_class !== d.asset_class || s.poll_interval !== d.poll_interval;
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
    setDraft((prev) => [...prev, { ticker: t, asset_class: assetClass, poll_interval: "1h" }]);
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

  async function commit(): Promise<void> {
    const savedByTicker = new Map(saved.map((s) => [s.ticker, s]));
    const draftByTicker = new Map(draft.map((d) => [d.ticker, d]));

    const toAdd = draft.filter((d) => !savedByTicker.has(d.ticker));
    const toRemove = saved.filter((s) => !draftByTicker.has(s.ticker));
    const toUpdate = draft.filter((d) => {
      const s = savedByTicker.get(d.ticker);
      return s !== undefined && s.poll_interval !== d.poll_interval;
    });

    try {
      await Promise.all([
        ...toAdd.map((d) => api.addToWatchlist(d.ticker, d.asset_class, d.poll_interval)),
        ...toRemove.map((s) => api.removeFromWatchlist(s.ticker)),
        ...toUpdate.map((d) => api.updateWatchlistItem(d.ticker, { poll_interval: d.poll_interval })),
      ]);
    } finally {
      // Resync with whatever actually landed, whether commit succeeded outright or
      // partially failed (Promise.all rejects on the first failure but earlier calls
      // may already have applied) — never leave the draft/saved baseline stale.
      await load();
    }
  }

  return { draft, loaded, error, dirty, addTicker, removeTicker, toggleInterval, commit };
}
