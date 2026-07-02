export interface AccessTokenClaims {
  sub: string;
  role: string;
  exp: number;
  [key: string]: unknown;
}

/**
 * Decodes the JWT payload client-side WITHOUT verifying the signature.
 * Used only to read the role/user id for UI nav gating — the backend
 * independently verifies the signature and enforces the role on every request.
 */
export function decodeAccessToken(token: string | null): AccessTokenClaims | null {
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
    const json = decodeURIComponent(
      atob(padded)
        .split("")
        .map((c) => "%" + c.charCodeAt(0).toString(16).padStart(2, "0"))
        .join(""),
    );
    return JSON.parse(json) as AccessTokenClaims;
  } catch {
    return null;
  }
}
