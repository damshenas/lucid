/**
 * Tiny global store tracking whether the backend is reachable. Updated by
 * api/client.ts's request() on every fetch (network failure -> offline; any response
 * at all, even a non-2xx, -> online, since that still proves the server answered).
 * Consumed by components/ServerStatusGate.tsx to gray out the whole app when offline.
 */

type Listener = () => void;

let online = true;
const listeners = new Set<Listener>();

export function getServerOnline(): boolean {
  return online;
}

export function setServerOnline(value: boolean): void {
  if (value === online) return;
  online = value;
  for (const listener of listeners) listener();
}

export function subscribeServerStatus(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
