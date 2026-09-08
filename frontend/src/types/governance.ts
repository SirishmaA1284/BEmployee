export type PolicyType = "MONEY_THRESHOLD" | "APPROVAL_ROLES";

export interface PolicyRead {
  id: string;
  policy_type: PolicyType;
  key: string;
  value: Record<string, unknown>;
  description: string | null;
  is_active: boolean;
  updated_at: string;
}

export type ApprovalStatus = "PENDING" | "APPROVED" | "REJECTED";

export interface ApprovalRequestRead {
  id: string;
  action: string;
  summary: string | null;
  payload: Record<string, unknown>;
  risk_level: "LOW" | "MEDIUM" | "HIGH";
  target_type: string | null;
  target_id: string | null;
  status: ApprovalStatus;
  requested_by_user_id: string;
  resolved_by_user_id: string | null;
  resolved_at: string | null;
  decision_note: string | null;
  created_at: string;
}

export type AuditAction =
  | "LOGIN"
  | "BUSINESS_CREATE"
  | "MEMBER_INVITE"
  | "PRODUCT_CREATE"
  | "PRODUCT_UPDATE"
  | "PRODUCT_DELETE"
  | "INVENTORY_ADJUST"
  | "CUSTOMER_CREATE"
  | "SUPPLIER_CREATE"
  | "SUPPLIER_LINK"
  | "ORDER_CREATE"
  | "ORDER_CANCEL"
  | "INVOICE_PAY"
  | "PURCHASE_ORDER_CREATE"
  | "PURCHASE_ORDER_SEND"
  | "PURCHASE_ORDER_RECEIVE"
  | "PURCHASE_ORDER_CANCEL"
  | "POLICY_UPSERT"
  | "APPROVAL_DECIDE"
  | "AGENT_ACTION"
  | "NOTIFICATION_SENT";

export interface AuditLogRead {
  id: string;
  actor_type: "USER" | "AGENT";
  actor_user_id: string | null;
  action: AuditAction;
  target_type: string | null;
  target_id: string | null;
  summary: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
}

export type NotificationType =
  | "LOW_STOCK"
  | "FORECASTED_STOCKOUT"
  | "APPROVAL_PENDING"
  | "DAILY_REPORT";

export type NotificationSeverity = "INFO" | "WARNING" | "CRITICAL";

export interface NotificationRead {
  id: string;
  notification_type: NotificationType;
  severity: NotificationSeverity;
  channel: string;
  title: string;
  message: string;
  payload: Record<string, unknown> | null;
  target_type: string | null;
  target_id: string | null;
  created_at: string;
}
