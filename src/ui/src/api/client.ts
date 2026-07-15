import type {
  AdminUser,
  BacktestResult,
  CredentialCatalogItem,
  Decision,
  FetchActivityRow,
  GitSyncResult,
  Job,
  MyCredentials,
  Order,
  Position,
  PriceBars,
  PriceCoverageRow,
  SettingsSchema,
  Signal,
  Strategy,
  Tokens,
  WatchlistItem,
} from "../types";
import { setServerOnline } from "../lib/serverStatus";
import { markSessionExpired } from "../lib/sessionExpiry";

const TOKEN_KEY = "lucid_access_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch (err) {
    // Network-level failure (server down/unreachable, DNS, CORS, offline) — anything
    // else (including a 4xx/5xx) means the server did answer, so only this branch
    // flips the app into the "server unreachable" gray-out state.
    setServerOnline(false);
    throw err;
  }
  setServerOnline(true);

  if (!response.ok) {
    // Only a *previously authenticated* request (one that actually sent a token)
    // failing with 401 means the session itself expired/was invalidated — a bare
    // login/setup attempt with no token yet also 401s on wrong credentials, which
    // is a normal inline form error, not a session expiry (see pages/Login.tsx).
    if (response.status === 401 && token) {
      setToken(null);
      markSessionExpired();
    }
    const detail = await response.text();
    throw new Error(`${response.status}: ${detail}`);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  status: () => request<{ initialized: boolean }>("/api/v1/auth/status"),
  setup: (username: string, password: string) =>
    request<Tokens>("/api/v1/auth/setup", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  login: (username: string, password: string) =>
    request<Tokens>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  positions: () => request<Position[]>("/api/v1/positions"),
  strategies: (direction?: "buy" | "sell") =>
    request<Strategy[]>(
      direction ? `/api/v1/strategies?direction=${direction}` : "/api/v1/strategies",
    ),
  scanStrategies: () =>
    request<{ scanned: number }>("/api/v1/strategies/scan", { method: "POST" }),
  activateStrategy: (name: string, direction: string) =>
    request(`/api/v1/strategies/${name}/activate?direction=${direction}`, {
      method: "PATCH",
    }),
  strategyDecisions: (name: string, limit = 50, offset = 0) =>
    request<Decision[]>(
      `/api/v1/strategies/${encodeURIComponent(name)}/decisions?limit=${limit}&offset=${offset}`,
    ),
  settingsSchema: () => request<SettingsSchema>("/api/v1/settings/schema"),
  settingsValues: () => request<Record<string, unknown>>("/api/v1/settings"),
  saveSettings: (values: Record<string, unknown>) =>
    request<{ ok: boolean }>("/api/v1/settings", {
      method: "POST",
      body: JSON.stringify({ values }),
    }),
  syncPositions: (assetClass = "equity") =>
    request<{ synced: number; closed: number }>(
      `/api/v1/positions/sync?asset_class=${encodeURIComponent(assetClass)}`,
      { method: "POST" },
    ),
  orders: (limit = 50, offset = 0) =>
    request<Order[]>(`/api/v1/orders?limit=${limit}&offset=${offset}`),
  placeManualOrder: (body: { ticker: string; side: "buy" | "sell"; quantity: number; asset_class: string }) =>
    request<Order>("/api/v1/orders/manual", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  signals: (limit = 50, offset = 0, source?: string) =>
    request<Signal[]>(
      `/api/v1/signals?limit=${limit}&offset=${offset}${source ? `&source=${encodeURIComponent(source)}` : ""}`,
    ),
  priceBars: (ticker: string, interval = "1d", limit = 250) =>
    request<PriceBars>(
      `/api/v1/prices/${encodeURIComponent(ticker)}?interval=${encodeURIComponent(interval)}&limit=${limit}`,
    ),
  backfillPrices: (ticker: string, days = 365) =>
    request<{ rows: number }>("/api/v1/prices/backfill", {
      method: "POST",
      body: JSON.stringify({ ticker, days }),
    }),
  watchlist: () => request<WatchlistItem[]>("/api/v1/prices/watchlist"),
  addToWatchlist: (
    ticker: string,
    assetClass: string,
    pollInterval: "1m" | "1h" = "1h",
    region: "us" | "eu" | "em" = "us",
  ) =>
    request<WatchlistItem>("/api/v1/prices/watchlist", {
      method: "POST",
      body: JSON.stringify({
        ticker,
        asset_class: assetClass,
        poll_interval: pollInterval,
        region,
      }),
    }),
  updateWatchlistItem: (
    ticker: string,
    changes: { enabled?: boolean; poll_interval?: "1m" | "1h"; region?: "us" | "eu" | "em" },
  ) =>
    request<WatchlistItem>(`/api/v1/prices/watchlist/${encodeURIComponent(ticker)}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),
  removeFromWatchlist: (ticker: string) =>
    request<void>(`/api/v1/prices/watchlist/${encodeURIComponent(ticker)}`, {
      method: "DELETE",
    }),
  runBacktest: (ticker: string, interval = "1d", strategy?: string) =>
    request<BacktestResult>("/api/v1/backtesting/run", {
      method: "POST",
      body: JSON.stringify({ ticker, interval, strategy: strategy || undefined }),
    }),
  adminUsers: () => request<AdminUser[]>("/api/v1/admin/users"),
  createAdminUser: (username: string, password: string, role: string) =>
    request<AdminUser>("/api/v1/admin/users", {
      method: "POST",
      body: JSON.stringify({ username, password, role }),
    }),
  updateAdminUser: (id: number, changes: { role?: string; is_active?: boolean }) =>
    request<AdminUser>(`/api/v1/admin/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),
  resetUserPassword: (id: number, newPassword: string) =>
    request<{ ok: boolean }>(`/api/v1/admin/users/${id}/reset-password`, {
      method: "POST",
      body: JSON.stringify({ new_password: newPassword }),
    }),
  deleteAdminUser: (id: number) =>
    request<void>(`/api/v1/admin/users/${id}`, { method: "DELETE" }),
  adminJobs: () => request<Job[]>("/api/v1/admin/jobs"),
  priceCoverageReport: () =>
    request<PriceCoverageRow[]>("/api/v1/admin/reports/price-coverage"),
  fetchActivityReport: (days = 7) =>
    request<FetchActivityRow[]>(`/api/v1/admin/reports/fetch-activity?days=${days}`),
  gitSync: () => request<GitSyncResult>("/api/v1/admin/git-sync", { method: "POST" }),
  changePassword: (newPassword: string) =>
    request<{ ok: boolean }>("/api/v1/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ new_password: newPassword }),
    }),
  systemCredentials: () => request<CredentialCatalogItem[]>("/api/v1/credentials/system"),
  setSystemCredential: (key: string, value: string) =>
    request<void>("/api/v1/credentials/system", {
      method: "POST",
      body: JSON.stringify({ key, value }),
    }),
  myCredentials: () => request<MyCredentials>("/api/v1/credentials/mine"),
  setMyCredential: (key: string, value: string) =>
    request<void>("/api/v1/credentials/mine", {
      method: "POST",
      body: JSON.stringify({ key, value }),
    }),
  setUseDefaultCredentials: (useDefault: boolean) =>
    request<void>("/api/v1/credentials/mine/use-default", {
      method: "PATCH",
      body: JSON.stringify({ use_default_credentials: useDefault }),
    }),
};
