import { useEffect, useState } from "react";
import { FlaskConical } from "lucide-react";
import { api } from "../api/client";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Select } from "../components/ui/Select";
import type { BacktestResult, Strategy } from "../types";

const INTERVALS = ["1d", "15m"];

export function Backtesting() {
  const [ticker, setTicker] = useState("");
  const [interval, setInterval_] = useState("1d");
  const [strategy, setStrategy] = useState("");
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    api
      .strategies("buy")
      .then(setStrategies)
      .catch(() => {});
  }, []);

  async function run() {
    if (!ticker.trim()) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await api.runBacktest(ticker.trim().toUpperCase(), interval, strategy || undefined),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="animate-fade-in-up space-y-4">
      <h2 className="text-xl font-semibold tracking-tight">Backtesting</h2>

      <Card className="space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <label className="block">
            <span className="mb-1 block text-xs text-white/40">Ticker</span>
            <input
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="AAPL"
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
          <label className="block">
            <span className="mb-1 block text-xs text-white/40">Strategy</span>
            <Select value={strategy} onChange={(e) => setStrategy(e.target.value)} className="w-40">
              <option value="" className="bg-surface">
                Active strategy
              </option>
              {strategies.map((s) => (
                <option key={s.name} value={s.name} className="bg-surface">
                  {s.name}
                </option>
              ))}
            </Select>
          </label>
          <Button onClick={run} disabled={running || !ticker.trim()}>
            <FlaskConical size={16} />
            {running ? "Running…" : "Run"}
          </Button>
        </div>
        <p className="text-xs text-white/40">
          Replays the selected buy strategy over stored bars and counts how many buy signals it
          would have produced. Requires at least 200 stored bars for the ticker.
        </p>
      </Card>

      {error && (
        <p className="rounded-xl border border-rose/30 bg-rose/10 px-3 py-2 text-sm text-rose">
          {error}
        </p>
      )}

      {result && (
        <Card className="flex flex-wrap gap-6">
          <div>
            <p className="text-xs text-white/40">Ticker</p>
            <p className="text-lg font-semibold">{result.ticker}</p>
          </div>
          <div>
            <p className="text-xs text-white/40">Strategy</p>
            <p className="text-lg font-semibold">{result.strategy ?? "—"}</p>
          </div>
          <div>
            <p className="text-xs text-white/40">Buy signals</p>
            <p className="text-lg font-semibold text-cyan">{result.buy_signals}</p>
          </div>
        </Card>
      )}
    </div>
  );
}
