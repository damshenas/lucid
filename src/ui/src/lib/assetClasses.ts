/** Mirrors AssetClass in src/conf/schema.py — kept as a fixed list (used by both the
 * Positions sync target and the Prices watchlist "add ticker" form) so values are
 * always one of the backend's known asset classes rather than free text. */
export const ASSET_CLASSES = ["equity", "commodity", "crypto", "fx"];
