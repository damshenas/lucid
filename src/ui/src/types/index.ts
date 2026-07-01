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
