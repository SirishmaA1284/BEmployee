import { apiClient } from "./client";
import type {
  AgentSessionDetail,
  AgentSessionSummary,
  ChatResponse,
} from "../types/agent";

export async function sendChatMessage(message: string) {
  const { data } = await apiClient.post<ChatResponse>("/api/agent/chat", { message });
  return data;
}

export async function listAgentSessions() {
  const { data } = await apiClient.get<AgentSessionSummary[]>("/api/agent/sessions");
  return data;
}

export async function getAgentSession(sessionId: string) {
  const { data } = await apiClient.get<AgentSessionDetail>(`/api/agent/sessions/${sessionId}`);
  return data;
}