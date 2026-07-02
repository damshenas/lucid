import { useEffect, useState } from "react";
import { ArrowDownRight, ArrowUpRight, ChevronLeft, ChevronRight, Inbox } from "lucide-react";
import { api } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import type { Signal } from "../types";

const PAGE_SIZE = 50;

const STATUS_TONE: Record<string, "cyan" | "rose" | "neutral"> = {
  acted_on: "cyan",
  blocked: "rose",
};

export function Signals() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .signals(PAGE_SIZE, offset)
      .then(setSignals)
      .catch((e) => setError((e as Error).message));
  }, [offset]);

  return (
    <div className="animate-fade-in-up space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold tracking-tight">Signals</h2>
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
          <p className="text-sm">No signals.</p>
        </Card>
      ) : (
        <Card className="overflow-hidden !p-0">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-white/10 text-white/40">
              <tr>
                <th className="px-4 py-3 font-medium">Ticker</th>
                <th className="px-4 py-3 font-medium">Direction</th>
                <th className="px-4 py-3 font-medium">Confidence</th>
                <th className="px-4 py-3 font-medium">Source</th>
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
                  <td className="px-4 py-3 text-white/60">{s.source}</td>
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
