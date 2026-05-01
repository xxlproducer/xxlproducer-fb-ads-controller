import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";

interface User {
  id: number;
  username: string;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  setupRequired: boolean | null;
  refresh: () => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  setup: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [setupRequired, setSetupRequired] = useState<boolean | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const status = await api.get<{ setup_required: boolean }>("/auth/setup-status");
      setSetupRequired(status.data.setup_required);
      if (status.data.setup_required) {
        setUser(null);
      } else {
        try {
          const me = await api.get<User>("/auth/me");
          setUser(me.data);
        } catch {
          setUser(null);
        }
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    const res = await api.post<User>("/auth/login", { username, password });
    setUser(res.data);
    setSetupRequired(false);
  }, []);

  const setup = useCallback(async (username: string, password: string) => {
    await api.post<User>("/auth/setup", { username, password });
    await login(username, password);
  }, [login]);

  const logout = useCallback(async () => {
    await api.post("/auth/logout");
    setUser(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({ user, loading, setupRequired, refresh, login, setup, logout }),
    [user, loading, setupRequired, refresh, login, setup, logout],
  );

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
