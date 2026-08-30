"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, ApiError, AuthUser } from "./api";
import {
  authenticateNativeSession,
  clearNativeSession,
  isNativeAndroid,
  restoreNativeSession,
  saveNativeSession,
} from "./mobile";

type AuthContextValue = {
  user: AuthUser | null;
  loading: boolean;
  locked: boolean;
  login: (username: string, password: string) => Promise<void>;
  loginWithFacebook: () => Promise<string | null>;
  unlock: (username: string, pin: string) => Promise<void>;
  unlockWithBiometric: () => Promise<void>;
  lock: () => void;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const LOCK_STORAGE_KEY = "sstore-locked";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [locked, setLocked] = useState(false);

  const refresh = useCallback(async () => {
    const timeout = window.setTimeout(() => setLoading(false), 10_000);
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
      window.clearTimeout(timeout);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void (async () => {
        if (isNativeAndroid()) {
          try {
            const session = await restoreNativeSession();
            if (session) {
              const me = await api.me();
              setUser(me);
              setLocked(true);
              setLoading(false);
              return;
            }
          } catch {
            await clearNativeSession();
          }
        }
        await refresh();
        if (window.sessionStorage.getItem(LOCK_STORAGE_KEY) === "1") setLocked(true);
      })();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    const me = await api.login(username, password);
    if (isNativeAndroid() && me.session_token) await saveNativeSession({ token: me.session_token, username: me.username });
    setUser(me);
    setLocked(false);
  }, []);

  const loginWithFacebook = useCallback(async () => {
    if (!isNativeAndroid()) return null;
    const { SocialLogin } = await import("@capgo/capacitor-social-login");
    const appId = process.env.NEXT_PUBLIC_META_APP_ID?.trim();
    const clientToken = process.env.NEXT_PUBLIC_META_CLIENT_TOKEN?.trim();
    if (!appId || !clientToken) throw new Error("ต้องกำหนด NEXT_PUBLIC_META_APP_ID และ NEXT_PUBLIC_META_CLIENT_TOKEN ก่อน build Android");
    await SocialLogin.initialize({ facebook: { appId, clientToken } });
    const result = await SocialLogin.login({
      provider: "facebook",
      options: { permissions: ["public_profile", "pages_show_list", "pages_read_engagement", "pages_manage_metadata", "pages_messaging"] },
    });
    const accessToken = result.result.accessToken?.token;
    if (!accessToken || result.result.isLimitedLogin) throw new Error("Facebook ไม่ได้มอบ access token ที่ใช้เชื่อม Page ได้");
    const loginResult = await api.nativeFacebookLogin(accessToken);
    const { user: me } = loginResult;
    if (!me.session_token) throw new Error("แอปไม่ได้รับ session จาก SStore");
    await saveNativeSession({ token: me.session_token, username: me.username });
    setUser(me);
    setLocked(false);
    return loginResult.attempt_id;
  }, []);

  const unlock = useCallback(async (username: string, pin: string) => {
    const me = await api.unlock(username, pin);
    if (isNativeAndroid() && me.session_token) await saveNativeSession({ token: me.session_token, username: me.username });
    setUser(me);
    setLocked(false);
    window.sessionStorage.removeItem(LOCK_STORAGE_KEY);
  }, []);

  const unlockWithBiometric = useCallback(async () => {
    await authenticateNativeSession();
    const me = await api.me();
    setUser(me);
    setLocked(false);
  }, []);

  const lock = useCallback(() => {
    setLocked(true);
    window.sessionStorage.setItem(LOCK_STORAGE_KEY, "1");
  }, []);

  const logout = useCallback(async () => {
    await api.logout();
    if (isNativeAndroid()) await clearNativeSession();
    setUser(null);
    setLocked(false);
    window.sessionStorage.removeItem(LOCK_STORAGE_KEY);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, locked, login, loginWithFacebook, unlock, unlockWithBiometric, lock, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth ต้องถูกใช้ภายใน AuthProvider");
  return ctx;
}
