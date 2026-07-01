import { useEffect, useState } from "react";
import { Inbox } from "lucide-react";
import { api } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Card } from "../components/ui/Card";
import type { Position } from "../types";

export function Dashboard() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.positions().then(setPositions).catch((e) => setError((e as Error).message));
  }, []);

  return (
    <div className="animate-fade-in-up space-y-4">
      <h2 className="text-xl font-semibold tracking-tight">Positions</h2>

      {error && (
        <p className="rounded-xl border border-rose/30 bg-rose/10 px-3 py-2 text-sm text-rose">
          {error}
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
