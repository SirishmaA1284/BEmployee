import axios from "axios";
import type { AxiosError, InternalAxiosRequestConfig } from "axios";

import type { RefreshResponse } from "../types/auth";

const AUTH_TOKEN_KEY = "ai_employee_token";
const REFRESH_TOKEN_KEY = "ai_employee_refresh_token";
const ACTIVE_BUSINESS_KEY = "ai_employee_active_business_id";

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000",
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  const businessId = localStorage.getItem(ACTIVE_BUSINESS_KEY);
  if (businessId) {
    config.headers["X-Business-Id"] = businessId;
  }
  return config;
});

// A shared in-flight rotation so many parallel 401s (e.g. every page's
// initial fetch after the access token expired) trigger exactly one refresh
// instead of hammering the rate-limited refresh endpoint.
let refreshPromise: Promise<string | null> | null = null;

async function rotateTokens(): Promise<string | null> {
  if (refreshPromise) {
    return refreshPromise;
  }
  refreshPromise = (async () => {
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    if (!refreshToken) {
      return null;
    }
    try {
      const { data } = await axios.post<RefreshResponse>(
        `${apiClient.defaults.baseURL}/api/auth/refresh`,
        { refresh_token: refreshToken },
        { headers: { "Content-Type": "application/json" } }
      );
      storeToken(data.access_token);
      storeRefreshToken(data.refresh_token);
      return data.access_token;
    } catch {
      clearToken();
      clearRefreshToken();
      clearActiveBusinessId();
      window.dispatchEvent(new Event("auth:expired"));
      return null;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as
      | (InternalAxiosRequestConfig & { _retried?: boolean })
      | undefined;
    const url = config?.url ?? "";
    const isAuthEndpoint = url.includes("/api/auth/");
    // Expired access token: rotate once (if a refresh token exists) and
    // replay the original request with the fresh token.
    if (error.response?.status === 401 && config && !config._retried && !isAuthEndpoint) {
      const newToken = await rotateTokens();
      if (newToken) {
        config._retried = true;
        return apiClient(config);
      }
    }
    return Promise.reject(error);
  }
);

export function getStoredToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function storeToken(token: string): void {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

export function getStoredRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function storeRefreshToken(token: string): void {
  localStorage.setItem(REFRESH_TOKEN_KEY, token);
}

export function clearRefreshToken(): void {
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function getStoredActiveBusinessId(): string | null {
  return localStorage.getItem(ACTIVE_BUSINESS_KEY);
}

export function storeActiveBusinessId(businessId: string): void {
  localStorage.setItem(ACTIVE_BUSINESS_KEY, businessId);
}

export function clearActiveBusinessId(): void {
  localStorage.removeItem(ACTIVE_BUSINESS_KEY);
}
