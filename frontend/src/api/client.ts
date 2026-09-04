import axios from "axios";

const AUTH_TOKEN_KEY = "ai_employee_token";
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

export function getStoredToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function storeToken(token: string): void {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY);
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
