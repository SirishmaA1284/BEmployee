export type BusinessRole = "OWNER" | "ADMIN" | "EMPLOYEE";

export interface UserRead {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
}

export interface BusinessRead {
  id: string;
  name: string;
  currency: string;
  role: BusinessRole;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: UserRead;
  businesses: BusinessRead[];
}

export interface RefreshResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface MeResponse {
  user: UserRead;
  businesses: BusinessRead[];
}

export interface BusinessMemberRead {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: BusinessRole;
}
