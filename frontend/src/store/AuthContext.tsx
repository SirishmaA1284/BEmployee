import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import * as authApi from "../api/auth";
import {
  clearActiveBusinessId,
  clearRefreshToken,
  clearToken,
  getStoredActiveBusinessId,
  getStoredRefreshToken,
  getStoredToken,
  storeActiveBusinessId,
  storeRefreshToken,
  storeToken,
} from "../api/client";
import type { BusinessRead, UserRead } from "../types/auth";

interface AuthContextValue {
  user: UserRead | null;
  businesses: BusinessRead[];
  activeBusinessId: string | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
  setActiveBusinessId: (businessId: string) => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserRead | null>(null);
  const [businesses, setBusinesses] = useState<BusinessRead[]>([]);
  const [activeBusinessId, setActiveBusinessIdState] = useState<string | null>(
    getStoredActiveBusinessId()
  );
  const [isLoading, setIsLoading] = useState(true);

  const setActiveBusinessId = useCallback((businessId: string) => {
    storeActiveBusinessId(businessId);
    setActiveBusinessIdState(businessId);
  }, []);

  const applySession = useCallback(
    (nextUser: UserRead, nextBusinesses: BusinessRead[]) => {
      setUser(nextUser);
      setBusinesses(nextBusinesses);
      if (!getStoredActiveBusinessId() && nextBusinesses.length > 0) {
        setActiveBusinessId(nextBusinesses[0].id);
      }
    },
    [setActiveBusinessId]
  );

  const refresh = useCallback(async () => {
    const token = getStoredToken();
    const refresh = getStoredRefreshToken();
    if (!token && !refresh) {
      setUser(null);
      setBusinesses([]);
      return;
    }
    try {
      // If the access token is present, refresh the session metadata from it;
      // otherwise rotate the stored refresh token to get a fresh access token.
      if (token) {
        const data = await authApi.me();
        applySession(data.user, data.businesses);
      } else if (refresh) {
        const data = await authApi.refreshToken(refresh);
        storeToken(data.access_token);
        storeRefreshToken(data.refresh_token);
        const me = await authApi.me();
        applySession(me.user, me.businesses);
      }
    } catch {
      clearToken();
      clearRefreshToken();
      clearActiveBusinessId();
      setUser(null);
      setBusinesses([]);
    }
  }, [applySession]);

  useEffect(() => {
    refresh().finally(() => setIsLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // When the refresh token is gone (expired/revoked), the API client clears
  // the stored session and signals it so the UI drops to the login page.
  useEffect(() => {
    const onExpired = () => {
      clearToken();
      clearRefreshToken();
      clearActiveBusinessId();
      setUser(null);
      setBusinesses([]);
    };
    window.addEventListener("auth:expired", onExpired);
    return () => window.removeEventListener("auth:expired", onExpired);
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const data = await authApi.login(email, password);
      storeToken(data.access_token);
      storeRefreshToken(data.refresh_token);
      applySession(data.user, data.businesses);
    },
    [applySession]
  );

  const registerAccount = useCallback(
    async (email: string, password: string, fullName: string) => {
      const data = await authApi.register(email, password, fullName);
      storeToken(data.access_token);
      storeRefreshToken(data.refresh_token);
      applySession(data.user, data.businesses);
    },
    [applySession]
  );

  const logout = useCallback(() => {
    // Best-effort: revoke the refresh token server-side, then clear local state
    // regardless of the network outcome.
    const refresh = getStoredRefreshToken();
    if (refresh) {
      authApi.logout(refresh).catch(() => undefined);
    }
    clearToken();
    clearRefreshToken();
    clearActiveBusinessId();
    setUser(null);
    setBusinesses([]);
  }, []);

  const value = useMemo(
    () => ({
      user,
      businesses,
      activeBusinessId,
      isLoading,
      login,
      register: registerAccount,
      logout,
      refresh,
      setActiveBusinessId,
    }),
    [user, businesses, activeBusinessId, isLoading, login, registerAccount, logout, refresh, setActiveBusinessId]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
