"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, ApiError, AuthUser } from "./api";

type AuthContextValue = {
  user: AuthUser | null;
  loading: boolean;
  locked: boolean;
  login: (username: string, password: string) => Promise<void>;
  unlock: (username: string, pin: string) => Promise<void>;
  lock: () => void;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const LOCK_STORAGE_KEY = "shop-sys-locked";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [locked, setLocked] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const me = await api.me();
      setUser(me);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setUser(null);
      } else {
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refresh();
      if (window.sessionStorage.getItem(LOCK_STORAGE_KEY) === "1") setLocked(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    const me = await api.login(username, password);
    setUser(me);
    setLocked(false);
  }, []);

  const unlock = useCallback(async (username: string, pin: string) => {
    const me = await api.unlock(username, pin);
    setUser(me);
    setLocked(false);
    window.sessionStorage.removeItem(LOCK_STORAGE_KEY);
  }, []);

  const lock = useCallback(() => {
    setLocked(true);
    window.sessionStorage.setItem(LOCK_STORAGE_KEY, "1");
  }, []);

  const logout = useCallback(async () => {
    await api.logout();
    setUser(null);
    setLocked(false);
    window.sessionStorage.removeItem(LOCK_STORAGE_KEY);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, locked, login, unlock, lock, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth ต้องถูกใช้ภายใน AuthProvider");
  return ctx;
}
