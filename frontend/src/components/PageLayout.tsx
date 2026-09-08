import { Link, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import { useAuth } from "../store/AuthContext";

const NAV_LINKS = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/chat", label: "AI Employee" },
  { to: "/orders", label: "Orders" },
  { to: "/inventory", label: "Inventory" },
  { to: "/suppliers", label: "Suppliers" },
  { to: "/purchase-orders", label: "Purchase Orders" },
  { to: "/approvals", label: "Approvals" },
  { to: "/alerts", label: "Alerts" },
  { to: "/documents", label: "Documents" },
  { to: "/policies", label: "Policies" },
];

export function NavBar() {
  const { user, businesses, activeBusinessId, setActiveBusinessId, logout } = useAuth();
  const location = useLocation();
  const activeBusiness = businesses.find((b) => b.id === activeBusinessId);

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-6 py-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-sm font-semibold">AI Employee Platform</p>
          <p className="text-xs text-slate-500">
            {user?.email}
            {activeBusiness && ` · ${activeBusiness.name} (${activeBusiness.role})`}
          </p>
        </div>

        <nav className="flex flex-wrap items-center gap-1">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className={`rounded-md px-3 py-1.5 text-sm ${
                location.pathname === link.to
                  ? "bg-slate-900 text-white"
                  : "text-slate-700 hover:bg-slate-100"
              }`}
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-3">
          {businesses.length > 0 && (
            <select
              value={activeBusinessId ?? ""}
              onChange={(e) => setActiveBusinessId(e.target.value)}
              className="rounded-md border border-slate-300 px-2 py-1.5 text-xs"
            >
              {businesses.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          )}
          <button
            onClick={logout}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50"
          >
            Log out
          </button>
        </div>
      </div>
    </header>
  );
}

export function PageLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen">
      <NavBar />
      <main className="mx-auto max-w-6xl space-y-8 px-6 py-8">{children}</main>
    </div>
  );
}