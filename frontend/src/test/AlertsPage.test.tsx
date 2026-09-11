import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AlertsPage } from "../pages/AlertsPage";

vi.mock("../api/governance", () => ({
  listNotifications: vi.fn(),
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
}));

vi.mock("../store/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "u1", email: "demo@example.com", full_name: "Demo", is_active: true },
    businesses: [{ id: "b1", name: "Demo Traders", currency: "INR", role: "OWNER" }],
    activeBusinessId: "b1",
    isLoading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
    setActiveBusinessId: vi.fn(),
  }),
}));

import { listNotifications } from "../api/governance";

const mockedList = vi.mocked(listNotifications);

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AlertsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AlertsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the empty state when there are no notifications", async () => {
    mockedList.mockResolvedValue([]);
    renderPage();
    expect(
      await screen.findByText(/No notifications yet/i)
    ).toBeInTheDocument();
  });

  it("renders a notification's title, severity and message", async () => {
    mockedList.mockResolvedValue([
      {
        id: "n1",
        notification_type: "LOW_STOCK",
        severity: "WARNING",
        channel: "IN_APP",
        title: "Low stock alert",
        message: "Coffee (COF-500) is at 3 units, below its threshold.",
        payload: null,
        target_type: "product",
        target_id: "p1",
        created_at: "2026-09-08T00:00:00Z",
        read: false,
      },
    ]);
    renderPage();
    // Wait for the actual notification card (title is unique vs. the filter
    // dropdown's "Low stock" option).
    expect(
      await screen.findByText("Coffee (COF-500) is at 3 units, below its threshold.")
    ).toBeInTheDocument();
    expect(screen.getByText("Low stock alert")).toBeInTheDocument();
    expect(screen.getByText("WARNING")).toBeInTheDocument();
  });
});