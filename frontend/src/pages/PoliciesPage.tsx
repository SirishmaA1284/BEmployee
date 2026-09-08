import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";

import { listPolicies, upsertPolicy } from "../api/governance";
import { PageLayout } from "../components/PageLayout";
import type { PolicyType } from "../types/governance";

export function PoliciesPage() {
  const queryClient = useQueryClient();
  const [policyType, setPolicyType] = useState<PolicyType>("MONEY_THRESHOLD");
  const [key, setKey] = useState("po_threshold");
  const [amount, setAmount] = useState("5000.00");
  const [description, setDescription] = useState("Purchase orders above this amount need approval");

  const policiesQuery = useQuery({ queryKey: ["policies"], queryFn: listPolicies });

  const upsertMutation = useMutation({
    mutationFn: () =>
      upsertPolicy({
        key,
        policy_type: policyType,
        value: policyType === "MONEY_THRESHOLD" ? { amount } : { roles: ["OWNER", "ADMIN"] },
        description: description || undefined,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["policies"] }),
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    upsertMutation.mutate();
  }

  const moneyPolicies = (policiesQuery.data ?? []).filter((p) => p.policy_type === "MONEY_THRESHOLD");

  return (
    <PageLayout>
      <h1 className="text-lg font-semibold">Policies</h1>
      <p className="text-sm text-slate-500">
        Configure how the system evaluates risk and decides when human approval is required.
      </p>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-semibold">Add / update policy</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-xs">
              Type
              <select
                value={policyType}
                onChange={(e) => setPolicyType(e.target.value as PolicyType)}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="MONEY_THRESHOLD">Money threshold</option>
                <option value="APPROVAL_ROLES">Approval roles</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs">
              Key
              <input
                value={key}
                onChange={(e) => setKey(e.target.value)}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
            {policyType === "MONEY_THRESHOLD" && (
              <label className="flex flex-col gap-1 text-xs">
                Amount
                <input
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className="rounded-md border border-slate-300 px-3 py-2 text-sm"
                />
              </label>
            )}
            <label className="flex flex-1 flex-col gap-1 text-xs">
              Description
              <input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
          </div>
          <button
            type="submit"
            disabled={upsertMutation.isPending}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {upsertMutation.isPending ? "Saving…" : "Save policy"}
          </button>
          {upsertMutation.isError && <p className="text-sm text-red-600">Could not save the policy.</p>}
        </form>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Configured policies</h2>
        {moneyPolicies.length === 0 && (
          <p className="text-sm text-slate-500">No money-threshold policies configured.</p>
        )}
        <ul className="space-y-2">
          {moneyPolicies.map((policy) => (
            <li key={policy.id} className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-medium">{policy.key}</span>
                <span className="text-xs text-slate-500">
                  {(policy.value as { amount?: string }).amount} · {policy.is_active ? "active" : "inactive"}
                </span>
              </div>
              {policy.description && <p className="mt-1 text-xs text-slate-500">{policy.description}</p>}
            </li>
          ))}
        </ul>
      </section>
    </PageLayout>
  );
}
