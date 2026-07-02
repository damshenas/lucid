export interface Tokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  must_change_password: boolean;
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
}

export interface SchemaField {
  type: string;
  default: unknown;
  required?: boolean;
  value: unknown;
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

export interface CredentialCatalogItem {
  key: string;
  label: string;
  secret: boolean;
  configured: boolean;
}

export interface MyCredentials {
  use_default_credentials: boolean;
  credentials: CredentialCatalogItem[];
}
