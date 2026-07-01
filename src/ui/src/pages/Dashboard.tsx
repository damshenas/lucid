import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Position } from "../types";

export function Dashboard() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.positions().then(setPositions).catch((e) => setError((e as Error).message));
  }, []);

  return (
    <div>
      <h2>Positions</h2>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      {positions.length === 0 ? (
        <p>No open positions.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Qty</th>
              <th>Avg price</th>
              <th>Class</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr key={p.ticker}>
                <td>{p.ticker}</td>
                <td>{p.quantity}</td>
                <td>{p.avg_price}</td>
                <td>{p.asset_class}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
