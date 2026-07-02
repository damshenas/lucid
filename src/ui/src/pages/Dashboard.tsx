import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowDownRight, ArrowUpRight, Briefcase, Radio, Receipt } from "lucide-react";
import { api } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Card } from "../components/ui/Card";
import type { Order, Position, Signal } from "../types";

export function Dashboard() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.positions(), api.signals(5, 0), api.orders(5, 0)])
      .then(([p, s, o]) => {
        setPositions(p);
        setSignals(s);
        setOrders(o);
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  return (
    <div className="animate-fade-in-up space-y-4">
      <h2 className="text-xl font-semibold tracking-tight">Dashboard</h2>

      {error && (
        <p className="rounded-xl border border-rose/30 bg-rose/10 px-3 py-2 text-sm text-rose">
          {error}
        </p>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Card className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet/15 text-violet">
            <Briefcase size={18} />
          </span>
          <div>
            <p className="text-xs text-white/40">Open positions</p>
            <p className="text-lg font-semibold">{positions.length}</p>
          </div>
        </Card>
        <Card className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan/15 text-cyan">
            <Radio size={18} />
          </span>
          <div>
            <p className="text-xs text-white/40">Recent signals</p>
            <p className="text-lg font-semibold">{signals.length}</p>
          </div>
        </Card>
        <Card className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-rose/15 text-rose">
            <Receipt size={18} />
          </span>
          <div>
            <p className="text-xs text-white/40">Recent orders</p>
            <p className="text-lg font-semibold">{orders.length}</p>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-white/40">
              Latest signals
            </h3>
            <Link to="/signals" className="text-xs font-medium text-violet hover:text-violet/80">
              View all
            </Link>
          </div>
          {signals.length === 0 ? (
            <p className="py-6 text-center text-sm text-white/40">No signals yet.</p>
          ) : (
            <div className="space-y-2">
              {signals.map((s, i) => (
                <div
                  key={`${s.ticker}-${i}`}
                  className="flex items-center justify-between rounded-xl border border-white/5 bg-white/5 px-3 py-2"
                >
                  <div className="flex items-center gap-2">
                    {s.direction === "buy" ? (
                      <ArrowUpRight size={16} className="text-cyan" />
                    ) : (
                      <ArrowDownRight size={16} className="text-rose" />
                    )}
                    <span className="text-sm font-medium">{s.ticker}</span>
                  </div>
                  <Badge tone={s.status === "acted_on" ? "cyan" : "neutral"}>{s.status}</Badge>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-white/40">
              Latest orders
            </h3>
            <Link to="/orders" className="text-xs font-medium text-violet hover:text-violet/80">
              View all
            </Link>
          </div>
          {orders.length === 0 ? (
            <p className="py-6 text-center text-sm text-white/40">No orders yet.</p>
          ) : (
            <div className="space-y-2">
              {orders.map((o, i) => (
                <div
                  key={`${o.ticker}-${i}`}
                  className="flex items-center justify-between rounded-xl border border-white/5 bg-white/5 px-3 py-2"
                >
                  <div className="flex items-center gap-2">
                    <Badge tone={o.side === "buy" ? "cyan" : "rose"}>{o.side}</Badge>
                    <span className="text-sm font-medium">{o.ticker}</span>
                  </div>
                  <span className="text-sm text-white/50">{o.status}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

