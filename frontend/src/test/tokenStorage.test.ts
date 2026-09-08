import { describe, expect, it } from "vitest";

import {
  clearRefreshToken,
  clearToken,
  getStoredRefreshToken,
  getStoredToken,
  storeRefreshToken,
  storeToken,
} from "../api/client";

describe("token storage helpers", () => {
  it("stores and retrieves the access token", () => {
    clearToken();
    expect(getStoredToken()).toBeNull();
    storeToken("abc.def.ghi");
    expect(getStoredToken()).toBe("abc.def.ghi");
    clearToken();
    expect(getStoredToken()).toBeNull();
  });

  it("stores and retrieves the refresh token independently", () => {
    clearToken();
    clearRefreshToken();
    storeToken("access-1");
    storeRefreshToken("refresh-1");
    expect(getStoredToken()).toBe("access-1");
    expect(getStoredRefreshToken()).toBe("refresh-1");
    clearRefreshToken();
    expect(getStoredRefreshToken()).toBeNull();
    expect(getStoredToken()).toBe("access-1");
  });
});