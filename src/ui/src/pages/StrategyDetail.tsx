import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Inbox,
  LineChart,
  XCircle,
} from "lucide-react";
import { api } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { humanize } from "./settings/schemaTree";
import type { Decision, Signal, Strategy } from "../types";

const PAGE_SIZE = 50;

const STATUS_TONE: Record<string, "cyan" | "rose" | "neutral"> = {
  acted_on: "cyan",
  blocked: "rose",
};

/**
 * Per-strategy page, linked from the sidebar for whichever strategy is currently
 * active (see hooks/useActiveStrategies.ts). What it shows beyond the strategy's own
 * info card depends entirely on that strategy's self-declared `features` (e.g.
 * trend_follow declares `["signals"]` — see strategies/buy/trend_follow.py) — not
 * every strategy produces the same kind of data.
 */
export function StrategyDetail() {
  const { name = "" } = useParams<{ name: string }>();
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoaded(false);
    setStrategy(null);
    api
      .strategies()
      .then((all) => setStrategy(all.find((s) => s.name === name) ?? null))
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoaded(true));
  }, [name]);

  return (
    <div className="animate-fade-in-up space-y-4">
      <h2 className="text-xl font-semibold tracking-tight">{humanize(name)}</h2>

      {error && (
        <p className="rounded-xl border border-rose/30 bg-rose/10 px-3 py-2 text-sm text-rose">
          {error}
        </p>
      )}

      {!loaded ? (
        <p className="py-6 text-center text-sm text-white/40">Loading…</p>
      ) : !strategy ? (
        <Card className="flex flex-col items-center gap-2 py-10 text-center text-white/50">
          <LineChart size={28} className="text-white/30" />
          <p className="text-sm">Strategy not found (it may no longer be active).</p>
        </Card>
      ) : (
        <>
          <Card>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold">{strategy.name}</span>
              <Badge tone={strategy.direction === "buy" ? "cyan" : "rose"}>{strategy.direction}</Badge>
              <Badge tone={strategy.is_builtin ? "violet" : "neutral"}>
                {strategy.is_builtin ? "native" : "custom"}
              </Badge>
            </div>
            {strategy.description && (
              <p className="mt-2 text-sm text-white/60">{strategy.description}</p>
            )}
            <p className="mt-1 text-xs text-white/40">v{strategy.version ?? "—"}</p>
          </Card>

          {strategy.features.includes("signals") && <StrategySignals source={strategy.name} />}

          <StrategyDecisions name={strategy.name} />
        </>
      )}
    </div>
  );
}

function StrategySignals({ source }: { source: string }) {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .signals(PAGE_SIZE, offset, source)
      .then(setSignals)
      .catch((e) => setError((e as Error).message));
  }, [offset, source]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-white/40">Signals</h3>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            disabled={offset === 0}
          >
            <ChevronLeft size={16} />
          </Button>
          <Button
            variant="secondary"
            onClick={() => setOffset((o) => o + PAGE_SIZE)}
            disabled={signals.length < PAGE_SIZE}
          >
            <ChevronRight size={16} />
          </Button>
        </div>
      </div>

      {error && (
        <p className="rounded-xl border border-rose/30 bg-rose/10 px-3 py-2 text-sm text-rose">
          {error}
        </p>
      )}

      {signals.length === 0 ? (
        <Card className="flex flex-col items-center gap-2 py-10 text-center text-white/50">
          <Inbox size={28} className="text-white/30" />
          <p className="text-sm">No signals yet.</p>
        </Card>
      ) : (
        <Card className="overflow-hidden !p-0">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-white/10 text-white/40">
              <tr>
                <th className="px-4 py-3 font-medium">Ticker</th>
                <th className="px-4 py-3 font-medium">Direction</th>
                <th className="px-4 py-3 font-medium">Confidence</th>
                <th className="px-4 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {signals.map((s, i) => (
                <tr key={`${s.ticker}-${i}`} className="transition-colors hover:bg-white/5">
                  <td className="px-4 py-3 font-medium">{s.ticker}</td>
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center gap-1">
                      {s.direction === "buy" ? (
                        <ArrowUpRight size={14} className="text-cyan" />
                      ) : (
                        <ArrowDownRight size={14} className="text-rose" />
                      )}
                      {s.direction}
                    </span>
                  </td>
                  <td className="px-4 py-3">{s.confidence}</td>
                  <td className="px-4 py-3">
                    <Badge tone={STATUS_TONE[s.status] ?? "neutral"}>{s.status}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

/** Every recorded change in this strategy's evaluation outcome — shown for every
 * strategy (buy or sell), unlike the feature-gated Signals section above, since
 * "why did/didn't it act" applies universally (see src/api/runtime.py
 * TradingRuntime._record_decision). */
function StrategyDecisions({ name }: { name: string }) {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .strategyDecisions(name, PAGE_SIZE, offset)
      .then(setDecisions)
      .catch((e) => setError((e as Error).message));
  }, [offset, name]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-white/40">Decisions</h3>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            disabled={offset === 0}
          >
            <ChevronLeft size={16} />
          </Button>
          <Button
            variant="secondary"
            onClick={() => setOffset((o) => o + PAGE_SIZE)}
            disabled={decisions.length < PAGE_SIZE}
          >
            <ChevronRight size={16} />
          </Button>
        </div>
      </div>

      {error && (
        <p className="rounded-xl border border-rose/30 bg-rose/10 px-3 py-2 text-sm text-rose">
          {error}
        </p>
      )}

      {decisions.length === 0 ? (
        <Card className="flex flex-col items-center gap-2 py-10 text-center text-white/50">
          <Inbox size={28} className="text-white/30" />
          <p className="text-sm">No decisions recorded yet — nothing evaluated this ticker yet.</p>
        </Card>
      ) : (
        <div className="space-y-2">
          {decisions.map((d, i) => (
            <Card key={`${d.ticker}-${d.created_at}-${i}`} className="!p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  {d.acted ? (
                    <CheckCircle2 size={16} className="shrink-0 text-cyan" />
                  ) : (
                    <XCircle size={16} className="shrink-0 text-white/30" />
                  )}
                  <span className="font-semibold">{d.ticker}</span>
                  <Badge tone={d.direction === "buy" ? "cyan" : "rose"}>{d.direction}</Badge>
                  <Badge tone={d.acted ? "cyan" : "neutral"}>{d.acted ? "acted" : "no action"}</Badge>
                </div>
                <span className="text-xs text-white/40">
                  {new Date(d.created_at).toLocaleString()}
                </span>
              </div>
              <p className="mt-2 text-sm text-white/70">{d.reasoning}</p>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
