import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "../api/governance";
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

function AlertCard({
  notification,
  onMarkRead,
  busy,
}: {
  notification: NotificationRead;
  onMarkRead: (id: string) => void;
  busy: boolean;
}) {
  return (
    <li
      className={`rounded-lg border px-4 py-3 ${
        SEVERITY_STYLES[notification.severity] ?? SEVERITY_STYLES.INFO
      } ${notification.read ? "opacity-70" : ""}`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium">
            {!notification.read && (
              <span
                className="mr-1.5 inline-block h-2 w-2 rounded-full bg-blue-500 align-middle"
                aria-label="unread"
              />
            )}
            {notification.title}
          </p>
          <p className="mt-0.5 text-xs text-slate-600">{notification.message}</p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-500 ring-1 ring-slate-200">
            {notification.severity}
          </span>
          {!notification.read && (
            <button
              onClick={() => onMarkRead(notification.id)}
              disabled={busy}
              className="rounded border border-slate-300 bg-white px-2 py-0.5 text-[10px] font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              Mark as read
            </button>
          )}
        </div>
      </div>
      <p className="mt-2 text-[10px] text-slate-400">
        {new Date(notification.created_at).toLocaleString()} · {notification.notification_type}
      </p>
    </li>
  );
}

export function AlertsPage() {
  const queryClient = useQueryClient();
  const [typeFilter, setTypeFilter] = useState("");
  const [unreadOnly, setUnreadOnly] = useState(false);

  const notificationsQuery = useQuery({
    queryKey: ["notifications", typeFilter, unreadOnly],
    queryFn: () => listNotifications(typeFilter || undefined, unreadOnly),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["notifications"] });
  };

  const markReadMutation = useMutation({
    mutationFn: (id: string) => markNotificationRead(id),
    onSuccess: invalidate,
  });

  const markAllMutation = useMutation({
    mutationFn: () => markAllNotificationsRead(),
    onSuccess: invalidate,
  });

  const notifications = notificationsQuery.data ?? [];
  const unreadCount = notifications.filter((n) => !n.read).length;

  return (
    <PageLayout>
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Alerts</h1>
        {unreadCount > 0 && (
          <button
            onClick={() => markAllMutation.mutate()}
            disabled={markAllMutation.isPending}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            Mark all as read ({unreadCount})
          </button>
        )}
      </div>
      <p className="text-sm text-slate-500">
        Proactive notifications from the scheduler: low stock, forecasted stockouts, pending
        approvals, and daily reports.
      </p>

      <div className="flex items-center gap-4">
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
        <label className="flex items-center gap-1.5 text-xs font-medium text-slate-600">
          <input
            type="checkbox"
            checked={unreadOnly}
            onChange={(e) => setUnreadOnly(e.target.checked)}
            className="rounded border-slate-300"
          />
          Unread only
        </label>
      </div>

      {notifications.length === 0 ? (
        <p className="text-sm text-slate-500">
          No notifications yet. The worker flags low stock, forecasted stockouts, and daily
          reports here as they happen.
        </p>
      ) : (
        <ul className="space-y-3">
          {notifications.map((n) => (
            <AlertCard
              key={n.id}
              notification={n}
              onMarkRead={(id) => markReadMutation.mutate(id)}
              busy={markReadMutation.isPending}
            />
          ))}
        </ul>
      )}
    </PageLayout>
  );
}