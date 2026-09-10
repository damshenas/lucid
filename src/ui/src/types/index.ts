export interface Tokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  must_change_password: boolean;
  password_policy_enforced: boolean;
}

export interface Position {
  ticker: string;
  quantity: number;
  avg_price: number;
  asset_class: string;
  status: string;
}

export interface Strategy {
  name: string;
  direction: string;
  version: string | null;
  is_builtin: boolean;
  description: string | null;
  file_path: string;
  /** UI feature tags the strategy declares itself (e.g. ["signals"]) — see
   * pages/StrategyDetail.tsx. */
  features: string[];
}

export interface SchemaField {
  type: string;
  default: unknown;
  required?: boolean;
  value: unknown;
  /** Allowed values for an "enum" type field — rendered as a dropdown when present. */
  choices?: string[];
}

export type SettingsSchema = Record<string, Record<string, SchemaField>>;

export interface Order {
  ticker: string;
  side: string;
  quantity: number;
  price: number | null;
  status: string;
  paper: boolean;
}

export interface Signal {
  ticker: string;
  direction: string;
  confidence: number;
  source: string;
  status: string;
  reasoning: string | null;
}

export interface Decision {
  ticker: string;
  direction: string;
  acted: boolean;
  reasoning: string;
  created_at: string;
}

export interface PriceBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface PriceBars {
  ticker: string;
  interval: string;
  bars: PriceBar[];
}

export interface WatchlistItem {
  ticker: string;
  asset_class: string;
  enabled: boolean;
  /** Intraday polling granularity for this ticker (Settings > Price > Watchlist) —
   * "1m" (green chip) or "1h" (blue chip, the default). Independent of the always-on
   * daily fetch every watchlist ticker gets regardless of this value. */
  poll_interval: "1m" | "1h";
  /** Which market-hours window (Settings > Price > Watchlist region chip) gates this
   * ticker's intraday fetch + strategy evaluation when market-hours gating is on —
   * "us" (default), "eu", or "em". Does not affect the always-on daily fetch. */
  region: "us" | "eu" | "em";
  has_bars: boolean;
  /** False for a ticker surfaced only because it has stored price bars on disk
   * (e.g. an ad-hoc backfill) but was never actually added to the watchlist — it
   * powers the ticker autocomplete (pages/Prices.tsx) but is NOT a real, saved
   * watchlist row: PATCH/DELETE on it 404s the same as any unknown ticker, so the
   * Settings > Watchlist UI must never treat it as pre-existing. */
  on_watchlist: boolean;
}

export interface BacktestResult {
  ticker: string;
  strategy: string | null;
  buy_signals: number;
}

export interface AdminUser {
  id: number;
  username: string;
  role: string;
  is_active?: boolean;
}

export interface Job {
  id: string;
  name: string;
  last_run: string | null;
  last_status: string | null;
  last_error: string | null;
}

export interface GitSyncResult {
  commit: string;
  deployed: string[];
}

export interface ResetTradingDataResult {
  reset: Record<string, { orders: number; signal_outcomes: number; signals: number; decisions: number; positions: number }>;
  synced: Record<string, Record<string, { synced?: number; closed?: number; error?: string }>>;
}

export interface PriceCoverageRow {
  ticker: string;
  interval: string;
  earliest: string;
  latest: string;
  bar_count: number;
}

export interface FetchActivityRow {
  ticker: string;
  interval: string;
  attempted_at: string | null;
  status: string;
  error_message: string | null;
  duration_seconds: number;
  rows_fetched: number;
}

export interface CredentialCatalogItem {
  key: string;
  label: string;
  platform: string;
  secret: boolean;
  configured: boolean;
}

export interface MyCredentials {
  use_default_credentials: boolean;
  credentials: CredentialCatalogItem[];
}
