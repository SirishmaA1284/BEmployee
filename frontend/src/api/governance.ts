import { apiClient } from "./client";
import type { ApprovalRequestRead, AuditLogRead, PolicyRead, PolicyType } from "../types/governance";

export async function listPolicies() {
  const { data } = await apiClient.get<PolicyRead[]>("/api/policies");
  return data;
}

export async function upsertPolicy(payload: {
  key: string;
  policy_type: PolicyType;
  value: Record<string, unknown>;
  description?: string;
  is_active?: boolean;
}) {
  const { data } = await apiClient.put<PolicyRead>(`/api/policies/${payload.key}`, payload);
  return data;
}

export async function listApprovalRequests(status?: string) {
  const { data } = await apiClient.get<ApprovalRequestRead[]>("/api/approvals", {
    params: status && status !== "ALL" ? { status_filter: status } : undefined,
  });
  return data;
}

export async function decideApproval(
  approvalId: string,
  decision: "approve" | "reject",
  decisionNote?: string
) {
  const { data } = await apiClient.post<ApprovalRequestRead>(
    `/api/approvals/${approvalId}/${decision}`,
    { decision_note: decisionNote }
  );
  return data;
}

export async function listAuditLogs(limit = 100) {
  const { data } = await apiClient.get<AuditLogRead[]>("/api/audit", { params: { limit } });
  return data;
}
