import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { decideApproval, listApprovalRequests } from "../api/governance";
import { PageLayout } from "../components/PageLayout";
import type { ApprovalRequestRead } from "../types/governance";

function StepBadges({ approval }: { approval: ApprovalRequestRead }) {
  return (
    <span className="text-xs text-slate-500">
      Stage {approval.current_stage} of {approval.required_stages}
      {approval.required_stages > 1 && (
        <span className="ml-1.5 text-[10px] text-slate-400">
          {approval.steps.map((s) => (
            <span key={s.id} className="mr-1">
              {s.status === "APPROVED" ? "✓" : s.status === "REJECTED" ? "✗" : "·"}
            </span>
          ))}
        </span>
      )}
    </span>
  );
}

export function ApprovalsPage() {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState("PENDING");

  const approvalsQuery = useQuery({
    queryKey: ["approvals", status],
    queryFn: () => listApprovalRequests(status),
  });

  const decideMutation = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "approve" | "reject" }) =>
      decideApproval(id, decision),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      queryClient.invalidateQueries({ queryKey: ["purchase-orders"] });
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      queryClient.invalidateQueries({ queryKey: ["inventory"] });
    },
  });

  const pending = (approvalsQuery.data ?? []).filter((a) => a.status === "PENDING");

  return (
    <PageLayout>
      <h1 className="text-lg font-semibold">Approvals</h1>
      <p className="text-sm text-slate-500">
        High-risk or policy-flagged actions wait here for a human decision before they run.
        Multi-stage requests need one approval per stage, by different people.
      </p>

      {pending.length > 0 && (
        <section>
          <h2 className="mb-3 text-lg font-semibold">Awaiting your decision</h2>
          <ul className="space-y-3">
            {pending.map((approval) => (
              <li key={approval.id} className="rounded-lg border border-slate-200 bg-white px-4 py-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">
                      {approval.action} · <span className="text-amber-600">{approval.risk_level} risk</span>
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      <StepBadges approval={approval} />
                      {" · "}
                      {approval.summary ?? "Proposed action"}
                      {approval.target_type && ` · target: ${approval.target_type}`}
                    </p>
                    <pre className="mt-2 max-h-40 overflow-auto rounded bg-slate-50 p-2 text-xs">
                      {JSON.stringify(approval.payload, null, 2)}
                    </pre>
                  </div>
                  <div className="flex flex-col gap-2">
                    <button
                      onClick={() => decideMutation.mutate({ id: approval.id, decision: "approve" })}
                      disabled={decideMutation.isPending}
                      className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                    >
                      Approve stage {approval.current_stage}
                    </button>
                    <button
                      onClick={() => decideMutation.mutate({ id: approval.id, decision: "reject" })}
                      disabled={decideMutation.isPending}
                      className="rounded-md border border-red-300 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
                    >
                      Reject
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
      {pending.length === 0 && (
        <p className="text-sm text-slate-500">No approvals awaiting a decision.</p>
      )}

      <section>
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-lg font-semibold">History</h2>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1 text-xs"
          >
            <option value="PENDING">Pending</option>
            <option value="APPROVED">Approved</option>
            <option value="REJECTED">Rejected</option>
            <option value="ALL">All</option>
          </select>
        </div>
        <ul className="space-y-2">
          {(approvalsQuery.data ?? []).map((approval) => (
            <li key={approval.id} className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-medium">{approval.action}</span>
                <span className="text-xs">
                  <StepBadges approval={approval} /> · {approval.status} · {approval.risk_level} risk
                </span>
              </div>
              {approval.decision_note && (
                <p className="mt-1 text-xs text-slate-500">Note: {approval.decision_note}</p>
              )}
            </li>
          ))}
        </ul>
      </section>
    </PageLayout>
  );
}