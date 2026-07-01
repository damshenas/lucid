import { useCallback, useEffect, useState } from "react";
import { api, getToken, setToken } from "../api/client";

export function useAuth() {
  const [token, setTokenState] = useState<string | null>(getToken());
  const [initialized, setInitialized] = useState<boolean | null>(null);

  useEffect(() => {
    api
      .status()
      .then((s) => setInitialized(s.initialized))
      .catch(() => setInitialized(null));
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const tokens = await api.login(username, password);
    setToken(tokens.access_token);
    setTokenState(tokens.access_token);
  }, []);

  const setup = useCallback(async (username: string, password: string) => {
    const tokens = await api.setup(username, password);
    setToken(tokens.access_token);
    setTokenState(tokens.access_token);
    setInitialized(true);
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setTokenState(null);
  }, []);

  return { token, initialized, login, setup, logout };
}
