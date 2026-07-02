import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Inbox } from "lucide-react";
import { api } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import type { Order } from "../types";

const PAGE_SIZE = 50;

export function Orders() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .orders(PAGE_SIZE, offset)
      .then(setOrders)
      .catch((e) => setError((e as Error).message));
  }, [offset]);

  return (
    <div className="animate-fade-in-up space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold tracking-tight">Orders</h2>
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
            disabled={orders.length < PAGE_SIZE}
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

      {orders.length === 0 ? (
        <Card className="flex flex-col items-center gap-2 py-10 text-center text-white/50">
          <Inbox size={28} className="text-white/30" />
          <p className="text-sm">No orders.</p>
        </Card>
      ) : (
        <Card className="overflow-hidden !p-0">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-white/10 text-white/40">
              <tr>
                <th className="px-4 py-3 font-medium">Ticker</th>
                <th className="px-4 py-3 font-medium">Side</th>
                <th className="px-4 py-3 font-medium">Qty</th>
                <th className="px-4 py-3 font-medium">Price</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Env</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {orders.map((o, i) => (
                <tr key={`${o.ticker}-${i}`} className="transition-colors hover:bg-white/5">
                  <td className="px-4 py-3 font-medium">{o.ticker}</td>
                  <td className="px-4 py-3">
                    <Badge tone={o.side === "buy" ? "cyan" : "rose"}>{o.side}</Badge>
                  </td>
                  <td className="px-4 py-3">{o.quantity}</td>
                  <td className="px-4 py-3">{o.price ?? "—"}</td>
                  <td className="px-4 py-3 text-white/60">{o.status}</td>
                  <td className="px-4 py-3">
                    <Badge tone="neutral">{o.paper ? "paper" : "live"}</Badge>
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
