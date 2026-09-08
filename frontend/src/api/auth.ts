import { apiClient } from "./client";
import type {
  BusinessMemberRead,
  BusinessRead,
  MeResponse,
  RefreshResponse,
  TokenResponse,
} from "../types/auth";

export async function refreshToken(refreshToken: string) {
  const { data } = await apiClient.post<RefreshResponse>("/api/auth/refresh", {
    refresh_token: refreshToken,
  });
  return data;
}

export async function logout(refreshToken: string) {
  await apiClient.post("/api/auth/logout", { refresh_token: refreshToken });
}

export async function register(email: string, password: string, fullName: string) {
  const { data } = await apiClient.post<TokenResponse>("/api/auth/register", {
    email,
    password,
    full_name: fullName,
  });
  return data;
}

export async function login(email: string, password: string) {
  const { data } = await apiClient.post<TokenResponse>("/api/auth/login", {
    email,
    password,
  });
  return data;
}

export async function me() {
  const { data } = await apiClient.get<MeResponse>("/api/auth/me");
  return data;
}

export async function createBusiness(name: string, currency = "INR") {
  const { data } = await apiClient.post<BusinessRead>("/api/businesses", { name, currency });
  return data;
}

export async function listMyBusinesses() {
  const { data } = await apiClient.get<BusinessRead[]>("/api/businesses");
  return data;
}

export async function listBusinessMembers() {
  const { data } = await apiClient.get<BusinessMemberRead[]>("/api/businesses/members");
  return data;
}

export async function inviteMember(email: string, role: "ADMIN" | "EMPLOYEE") {
  const { data } = await apiClient.post<BusinessMemberRead>("/api/businesses/members", {
    email,
    role,
  });
  return data;
}
