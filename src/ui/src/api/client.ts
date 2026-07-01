import type { Position, SettingsSchema, Strategy, Tokens } from "../types";

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

  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
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
  strategies: () => request<Strategy[]>("/api/v1/strategies"),
  scanStrategies: () =>
    request<{ scanned: number }>("/api/v1/strategies/scan", { method: "POST" }),
  activateStrategy: (name: string, direction: string) =>
    request(`/api/v1/strategies/${name}/activate?direction=${direction}`, {
      method: "PATCH",
    }),
  settingsSchema: () => request<SettingsSchema>("/api/v1/settings/schema"),
  saveSettings: (values: Record<string, unknown>) =>
    request<{ ok: boolean }>("/api/v1/settings", {
      method: "POST",
      body: JSON.stringify({ values }),
    }),
};
