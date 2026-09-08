import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { listNotifications } from "../api/governance";
import { PageLayout } from "../components/PageLayout";
import type { NotificationRead } from "../types/governance";

const SEVERITY_STYLES: Record<string, string> = {
  CRITICAL: "border-red-300 bg-red-50",
  WARNING: "border-amber-300 bg-amber-50",
  INFO: "border-slate-200 bg-white",
};

const TYPE_FILTERS = [
  { value: "", label: "All alerts" },
  { value: "LOW_STOCK", label: "Low stock" },
  { value: "FORECASTED_STOCKOUT", label: "Forecasted stockouts" },
  { value: "APPROVAL_PENDING", label: "Pending approvals" },
  { value: "DAILY_REPORT", label: "Daily reports" },
];

function AlertCard({ notification }: { notification: NotificationRead }) {
  return (
    <li
      className={`rounded-lg border px-4 py-3 ${
        SEVERITY_STYLES[notification.severity] ?? SEVERITY_STYLES.INFO
      }`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium">{notification.title}</p>
          <p className="mt-0.5 text-xs text-slate-600">{notification.message}</p>
        </div>
        <span className="shrink-0 rounded-full bg-white px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-500 ring-1 ring-slate-200">
          {notification.severity}
        </span>
      </div>
      <p className="mt-2 text-[10px] text-slate-400">
        {new Date(notification.created_at).toLocaleString()} · {notification.notification_type}
      </p>
    </li>
  );
}

export function AlertsPage() {
  const [typeFilter, setTypeFilter] = useState("");

  const notificationsQuery = useQuery({
    queryKey: ["notifications", typeFilter],
    queryFn: () => listNotifications(typeFilter || undefined),
  });

  const notifications = notificationsQuery.data ?? [];

  return (
    <PageLayout>
      <h1 className="text-lg font-semibold">Alerts</h1>
      <p className="text-sm text-slate-500">
        Proactive notifications from the scheduler: low stock, forecasted stockouts, pending
        approvals, and daily reports.
      </p>

      <div className="flex items-center gap-2">
        <label className="text-xs font-medium text-slate-600" htmlFor="type-filter">
          Filter
        </label>
        <select
          id="type-filter"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-1 text-xs"
        >
          {TYPE_FILTERS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
      </div>

      {notifications.length === 0 ? (
        <p className="text-sm text-slate-500">
          No notifications yet. The worker flags low stock, forecasted stockouts, and daily
          reports here as they happen.
        </p>
      ) : (
        <ul className="space-y-3">
          {notifications.map((n) => (
            <AlertCard key={n.id} notification={n} />
          ))}
        </ul>
      )}
    </PageLayout>
  );
}