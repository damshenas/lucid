import { useEffect, useSyncExternalStore } from "react";
import type { ReactNode } from "react";
import { WifiOff } from "lucide-react";
import { getServerOnline, setServerOnline, subscribeServerStatus } from "../lib/serverStatus";

const RETRY_INTERVAL_MS = 4000;

/**
 * Grays out (blurs + disables pointer events on) the entire app whenever the backend
 * is unreachable, and polls /health/live in the background to detect recovery — so the
 * UI never sits there looking "fine" while every request is silently failing.
 */
export function ServerStatusGate({ children }: { children: ReactNode }) {
  const online = useSyncExternalStore(subscribeServerStatus, getServerOnline);

  useEffect(() => {
    if (online) return;
    const id = setInterval(async () => {
      try {
        await fetch("/health/live");
        setServerOnline(true);
      } catch {
        // still unreachable — keep polling
      }
    }, RETRY_INTERVAL_MS);
    return () => clearInterval(id);
  }, [online]);

  return (
    <div className="relative min-h-screen">
      <div
        className={
          online
            ? ""
            : "pointer-events-none select-none opacity-60 grayscale blur-[2px] transition-all duration-300"
        }
        aria-hidden={!online}
      >
        {children}
      </div>
      {!online && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="glass flex flex-col items-center gap-2 rounded-2xl px-6 py-5 text-center">
            <WifiOff className="text-white/70" size={28} />
            <p className="text-sm font-semibold text-white">Server unreachable</p>
            <p className="text-xs text-white/50">Reconnecting automatically…</p>
          </div>
        </div>
      )}
    </div>
  );
}
