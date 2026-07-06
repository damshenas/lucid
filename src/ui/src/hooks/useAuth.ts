import { useCallback, useEffect, useMemo, useState } from "react";
import { api, getToken, setToken } from "../api/client";
import { decodeAccessToken } from "../lib/jwt";
import type { Role } from "../lib/permissions";
import { clearSessionExpired, subscribeSessionExpiry } from "../lib/sessionExpiry";

export function useAuth() {
  const [token, setTokenState] = useState<string | null>(getToken());
  const [initialized, setInitialized] = useState<boolean | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);

  useEffect(() => {
    api
      .status()
      .then((s) => setInitialized(s.initialized))
      .catch(() => setInitialized(null));
  }, []);

  // A 401 on any authenticated request (see api/client.ts's request()) means the
  // session died server-side — force the app back to Login from wherever the user
  // currently is, instead of leaving them on a page where every action just errors.
  useEffect(
    () =>
      subscribeSessionExpiry(() => {
        setTokenState(null);
        setSessionExpired(true);
      }),
    [],
  );

  const login = useCallback(async (username: string, password: string) => {
    const tokens = await api.login(username, password);
    setToken(tokens.access_token);
    setTokenState(tokens.access_token);
    setSessionExpired(false);
    clearSessionExpired();
  }, []);

  const setup = useCallback(async (username: string, password: string) => {
    const tokens = await api.setup(username, password);
    setToken(tokens.access_token);
    setTokenState(tokens.access_token);
    setInitialized(true);
    setSessionExpired(false);
    clearSessionExpired();
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setTokenState(null);
    setSessionExpired(false);
    clearSessionExpired();
  }, []);

  const claims = useMemo(() => decodeAccessToken(token), [token]);
  const role = (claims?.role as Role | undefined) ?? null;
  const userId = claims?.sub ?? null;

  return { token, role, userId, initialized, sessionExpired, login, setup, logout };
}
