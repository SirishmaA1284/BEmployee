export type AgentIntent =
  | "CREATE_ORDER"
  | "CHECK_INVENTORY"
  | "LOW_STOCK"
  | "COMPARE_SUPPLIERS"
  | "CREATE_PURCHASE_ORDER"
  | "SEARCH_PRODUCTS"
  | "SEARCH_CUSTOMERS"
  | "SALES_REPORT"
  | "UNKNOWN";

export type AgentSessionStatus =
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "NEEDS_CLARIFICATION";

export interface ChatResponse {
  session_id: string;
  intent: AgentIntent;
  agent_name: string;
  status: AgentSessionStatus;
  reply: string;
  result: Record<string, unknown> | null;
}

export interface AgentSessionSummary {
  id: string;
  intent: AgentIntent | null;
  agent_name: string | null;
  status: AgentSessionStatus;
  user_message: string;
  reply: string | null;
  created_at: string;
}

export interface AgentActionRead {
  id: string;
  tool_name: string;
  status: "SUCCESS" | "FAILED" | "REJECTED" | "PENDING";
  risk_level: "LOW" | "MEDIUM" | "HIGH";
  input_summary: Record<string, unknown>;
  result_summary: Record<string, unknown>;
  created_at: string;
}

export interface AgentTaskRead {
  id: string;
  agent_name: string | null;
  status: "RUNNING" | "COMPLETED" | "FAILED";
  started_at: string;
  completed_at: string | null;
  actions: AgentActionRead[];
}

export interface AgentSessionDetail {
  id: string;
  intent: AgentIntent | null;
  status: AgentSessionStatus;
  user_message: string;
  reply: string | null;
  created_at: string;
  completed_at: string | null;
  tasks: AgentTaskRead[];
}