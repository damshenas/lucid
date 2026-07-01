import { useEffect, useState } from "react";
import { LineChart, RefreshCw } from "lucide-react";
import { api } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import type { Strategy } from "../types";

export function Strategies() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [activating, setActivating] = useState<string | null>(null);

  async function refresh() {
    try {
      setStrategies(await api.strategies());
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function sync() {
    setSyncing(true);
    setError(null);
    try {
      await api.scanStrategies();
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSyncing(false);
    }
  }

  async function activate(s: Strategy) {
    setActivating(s.name);
    setError(null);
    try {
      await api.activateStrategy(s.name, s.direction);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setActivating(null);
    }
  }

  return (
    <div className="animate-fade-in-up space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold tracking-tight">Strategies</h2>
        <Button variant="secondary" onClick={sync} disabled={syncing}>
          <RefreshCw size={16} className={syncing ? "animate-spin" : ""} />
          Sync
        </Button>
      </div>

      {error && (
        <p className="rounded-xl border border-rose/30 bg-rose/10 px-3 py-2 text-sm text-rose">
          {error}
        </p>
      )}

      {strategies.length === 0 ? (
        <Card className="flex flex-col items-center gap-2 py-10 text-center text-white/50">
          <LineChart size={28} className="text-white/30" />
          <p className="text-sm">No strategies yet. Try syncing.</p>
        </Card>
      ) : (
        <div className="space-y-3">
          {strategies.map((s) => (
            <Card key={s.name} className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="truncate font-semibold">{s.name}</span>
                  <Badge tone={s.direction === "long" ? "cyan" : "rose"}>{s.direction}</Badge>
                  <Badge tone={s.is_builtin ? "violet" : "neutral"}>
                    {s.is_builtin ? "built-in" : "user"}
                  </Badge>
                </div>
                <p className="mt-1 text-xs text-white/40">v{s.version ?? "—"}</p>
              </div>
              <Button
                variant="secondary"
                onClick={() => activate(s)}
                disabled={activating === s.name}
                className="shrink-0"
              >
                {activating === s.name ? "Activating…" : "Set active"}
              </Button>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
