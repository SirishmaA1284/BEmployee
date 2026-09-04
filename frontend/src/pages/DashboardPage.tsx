import { useState } from "react";
import type { FormEvent } from "react";

import * as authApi from "../api/auth";
import { useAuth } from "../store/AuthContext";

export function DashboardPage() {
  const { user, businesses, activeBusinessId, setActiveBusinessId, logout, refresh } = useAuth();
  const [businessName, setBusinessName] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreateBusiness(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsCreating(true);
    try {
      const business = await authApi.createBusiness(businessName);
      setBusinessName("");
      await refresh();
      setActiveBusinessId(business.id);
    } catch {
      setError("Could not create business. Please try again.");
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-4">
          <div>
            <p className="text-sm font-semibold">AI Employee Platform</p>
            <p className="text-xs text-slate-500">Signed in as {user?.email}</p>
          </div>
          <button
            onClick={logout}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50"
          >
            Log out
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-4xl space-y-8 px-6 py-8">
        <section>
          <h2 className="mb-3 text-lg font-semibold">Your businesses</h2>
          {businesses.length === 0 ? (
            <p className="text-sm text-slate-500">
              You don't belong to any business yet. Create one below to get started.
            </p>
          ) : (
            <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
              {businesses.map((business) => (
                <li key={business.id} className="flex items-center justify-between px-4 py-3">
                  <div>
                    <p className="text-sm font-medium">{business.name}</p>
                    <p className="text-xs text-slate-500">
                      {business.currency} · role: {business.role}
                    </p>
                  </div>
                  {business.id === activeBusinessId ? (
                    <span className="rounded-full bg-slate-900 px-2.5 py-1 text-xs font-medium text-white">
                      Active
                    </span>
                  ) : (
                    <button
                      onClick={() => setActiveBusinessId(business.id)}
                      className="rounded-md border border-slate-300 px-2.5 py-1 text-xs hover:bg-slate-50"
                    >
                      Switch to this business
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <h2 className="mb-3 text-lg font-semibold">Create a business</h2>
          <form onSubmit={handleCreateBusiness} className="flex max-w-md gap-2">
            <input
              required
              placeholder="Business name"
              value={businessName}
              onChange={(e) => setBusinessName(e.target.value)}
              className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
            />
            <button
              type="submit"
              disabled={isCreating}
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
            >
              {isCreating ? "Creating..." : "Create"}
            </button>
          </form>
          {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        </section>

        <section className="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-500">
          Sales, inventory alerts, pending approvals, and AI employee activity land here in
          later phases (see <code>docs/decisions.md</code> roadmap) — this dashboard currently
          covers Phase 2 (accounts, businesses, membership) only.
        </section>
      </main>
    </div>
  );
}
