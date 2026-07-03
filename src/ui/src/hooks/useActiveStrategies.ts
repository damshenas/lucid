import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Strategy } from "../types";

/**
 * Currently *active* strategies (one per direction, at most) — used to build the
 * per-strategy sidebar entries (see components/AppLayout.tsx and
 * pages/StrategyDetail.tsx). Unlike `api.strategies()` (every discovered strategy,
 * browsable in Settings), this only returns whichever strategy each direction's
 * `strategy.active_{buy,sell}_strategy` config value currently points to.
 */
export function useActiveStrategies(): { strategies: Strategy[]; loaded: boolean } {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.strategies(), api.settingsValues()])
      .then(([all, values]) => {
        if (cancelled) return;
        const strategySection = (values.strategy as Record<string, unknown>) ?? {};
        const activeNames = new Set(
          [strategySection.active_buy_strategy, strategySection.active_sell_strategy].filter(
            (name): name is string => typeof name === "string" && name.length > 0,
          ),
        );
        setStrategies(all.filter((s) => activeNames.has(s.name)));
      })
      .catch(() => {
        if (!cancelled) setStrategies([]);
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { strategies, loaded };
}
