import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Strategy } from "../types";

export function Strategies() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [error, setError] = useState<string | null>(null);

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

  async function activate(s: Strategy) {
    await api.activateStrategy(s.name, s.direction);
    await refresh();
  }

  return (
    <div>
      <h2>Strategies</h2>
      <button onClick={() => api.scanStrategies().then(refresh)}>Sync strategies</button>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Direction</th>
            <th>Version</th>
            <th>Type</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {strategies.map((s) => (
            <tr key={s.name}>
              <td>{s.name}</td>
              <td>{s.direction}</td>
              <td>{s.version}</td>
              <td>{s.is_builtin ? "built-in" : "user"}</td>
              <td>
                <button onClick={() => activate(s)}>Set active</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
