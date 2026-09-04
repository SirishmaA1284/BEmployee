import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import * as authApi from "../api/auth";
import {
  clearActiveBusinessId,
  clearToken,
  getStoredActiveBusinessId,
  getStoredToken,
  storeActiveBusinessId,
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
    if (!getStoredToken()) {
      setUser(null);
      setBusinesses([]);
      return;
    }
    try {
      const data = await authApi.me();
      applySession(data.user, data.businesses);
    } catch {
      clearToken();
      clearActiveBusinessId();
      setUser(null);
      setBusinesses([]);
    }
  }, [applySession]);

  useEffect(() => {
    refresh().finally(() => setIsLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const data = await authApi.login(email, password);
      storeToken(data.access_token);
      applySession(data.user, data.businesses);
    },
    [applySession]
  );

  const registerAccount = useCallback(
    async (email: string, password: string, fullName: string) => {
      const data = await authApi.register(email, password, fullName);
      storeToken(data.access_token);
      applySession(data.user, data.businesses);
    },
    [applySession]
  );

  const logout = useCallback(() => {
    clearToken();
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
