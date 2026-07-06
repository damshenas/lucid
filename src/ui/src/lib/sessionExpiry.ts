/**
 * Tiny global store (same useSyncExternalStore pattern as lib/serverStatus.ts)
 * tracking whether the current session was just invalidated by the backend (401
 * on any request — expired/invalid JWT). api/client.ts's request() flips this (and
 * clears the stored token) on every 401; hooks/useAuth.ts consumes it to force the
 * app back to the Login screen from anywhere, instead of leaving the user stuck on
 * an authenticated-looking page where every action just errors.
 */

type Listener = () => void;

let expired = false;
const listeners = new Set<Listener>();

export function isSessionExpired(): boolean {
  return expired;
}

export function markSessionExpired(): void {
  if (expired) return;
  expired = true;
  for (const listener of listeners) listener();
}

export function clearSessionExpired(): void {
  if (!expired) return;
  expired = false;
  for (const listener of listeners) listener();
}

export function subscribeSessionExpiry(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
