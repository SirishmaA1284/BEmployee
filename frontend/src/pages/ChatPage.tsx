import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";

import { listAgentSessions, sendChatMessage } from "../api/agent";
import { PageLayout } from "../components/PageLayout";
import type { ChatResponse } from "../types/agent";

interface ConversationEntry {
  request: string;
  response: ChatResponse;
}

const EXAMPLE_PROMPTS = [
  "Create an order for Rahul with 3 coffee packets and 2 sugar bags",
  "Which products are running low?",
  "Which supplier gives the best price for coffee?",
  "Prepare a purchase order for everything likely to run out",
  "Give me a sales report",
];

function ResultView({ response }: { response: ChatResponse }) {
  const result = response.result;
  if (!result) return null;

  if (response.intent === "LOW_STOCK" || response.intent === "CHECK_INVENTORY") {
    const items = (result as { low_stock?: unknown[]; items?: unknown[] }).low_stock
      ?? (result as { items?: unknown[] }).items
      ?? [];
    if (items.length === 0) return null;
    return (
      <table className="mt-2 w-full text-left text-xs">
        <thead>
          <tr className="border-b border-slate-200 text-slate-500">
            <th className="py-1">Product</th>
            <th className="py-1">On hand</th>
            <th className="py-1">Threshold</th>
            <th className="py-1">Reorder qty</th>
          </tr>
        </thead>
        <tbody>
          {(items as Array<{ product_name: string; quantity_on_hand: number; reorder_threshold: number; reorder_quantity: number }>).map((item) => (
            <tr key={item.product_name} className="border-b border-slate-100">
              <td className="py-1">{item.product_name}</td>
              <td className="py-1">{item.quantity_on_hand}</td>
              <td className="py-1">{item.reorder_threshold}</td>
              <td className="py-1">{item.reorder_quantity}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  if (response.intent === "COMPARE_SUPPLIERS") {
    const offers = (result as { offers?: Array<{ supplier_name: string; is_active: boolean; price: string; lead_time_days: number }> }).offers ?? [];
    if (offers.length === 0) return null;
    return (
      <table className="mt-2 w-full text-left text-xs">
        <thead>
          <tr className="border-b border-slate-200 text-slate-500">
            <th className="py-1">Supplier</th>
            <th className="py-1">Price</th>
            <th className="py-1">Lead (days)</th>
          </tr>
        </thead>
        <tbody>
          {offers.map((offer) => (
            <tr key={offer.supplier_name} className="border-b border-slate-100">
              <td className="py-1">{offer.supplier_name}{!offer.is_active && " (inactive)"}</td>
              <td className="py-1">{offer.price}</td>
              <td className="py-1">{offer.lead_time_days}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  if (response.intent === "SALES_REPORT") {
    const report = result as Record<string, string | number>;
    return (
      <div className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
        {Object.entries(report).map(([key, value]) => (
          <div key={key} className="rounded-md border border-slate-200 px-3 py-2">
            <p className="text-slate-500">{key.replace(/_/g, " ")}</p>
            <p className="font-medium">{value}</p>
          </div>
        ))}
      </div>
    );
  }

  return null;
}

export function ChatPage() {
  const queryClient = useQueryClient();
  const [conversation, setConversation] = useState<ConversationEntry[]>([]);
  const [message, setMessage] = useState("");

  const sessionsQuery = useQuery({ queryKey: ["agent-sessions"], queryFn: listAgentSessions });

  const chatMutation = useMutation({
    mutationFn: sendChatMessage,
    onSuccess: (response) => {
      setConversation((entries) => [...entries, { request: message, response }]);
      setMessage("");
      queryClient.invalidateQueries({ queryKey: ["agent-sessions"] });
    },
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!message.trim() || chatMutation.isPending) return;
    chatMutation.mutate(message.trim());
  }

  return (
    <PageLayout>
      <h1 className="text-lg font-semibold">AI Employee</h1>
      <p className="text-sm text-slate-500">
        Ask the AI employee to do operational work — it executes safe actions and verifies them,
        leaving a full audit trail.
      </p>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="lg:col-span-2">
          <div className="flex min-h-[24rem] flex-col rounded-lg border border-slate-200 bg-white">
            <div className="flex-1 space-y-4 overflow-y-auto p-4">
              {conversation.length === 0 && (
                <div className="space-y-2 text-sm text-slate-500">
                  <p>Try one of these:</p>
                  <ul className="space-y-1">
                    {EXAMPLE_PROMPTS.map((prompt) => (
                      <li key={prompt}>
                        <button
                          onClick={() => {
                            setMessage(prompt);
                          }}
                          className="rounded-md border border-slate-200 px-2 py-1 text-xs hover:bg-slate-50"
                        >
                          {prompt}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {conversation.map((entry, index) => (
                <div key={index} className="space-y-2">
                  <div className="flex justify-end">
                    <div className="max-w-[85%] rounded-lg rounded-br-none bg-slate-900 px-3 py-2 text-sm text-white">
                      {entry.request}
                    </div>
                  </div>
                  <div className="flex justify-start">
                    <div className="max-w-[90%] rounded-lg rounded-bl-none border border-slate-200 px-3 py-2 text-sm">
                      <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-400">
                        {entry.response.agent_name} · {entry.response.intent} · {entry.response.status}
                      </p>
                      <p>{entry.response.reply}</p>
                      <ResultView response={entry.response} />
                    </div>
                  </div>
                </div>
              ))}
              {chatMutation.isPending && (
                <div className="flex justify-start">
                  <div className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-500">
                    Working…
                  </div>
                </div>
              )}
              {chatMutation.isError && (
                <p className="text-sm text-red-600">Something went wrong. Please try again.</p>
              )}
            </div>
            <form onSubmit={handleSubmit} className="flex gap-2 border-t border-slate-200 p-3">
              <input
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Ask the AI employee to do something…"
                className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
              />
              <button
                type="submit"
                disabled={chatMutation.isPending || !message.trim()}
                className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
              >
                Send
              </button>
            </form>
          </div>
        </section>

        <aside>
          <h2 className="mb-2 text-sm font-semibold">Recent activity</h2>
          <ul className="space-y-2">
            {sessionsQuery.data?.map((session) => (
              <li key={session.id} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{session.intent ?? "—"}</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                      session.status === "COMPLETED"
                        ? "bg-green-100 text-green-700"
                        : session.status === "FAILED"
                          ? "bg-red-100 text-red-700"
                          : "bg-amber-100 text-amber-700"
                    }`}
                  >
                    {session.status}
                  </span>
                </div>
                <p className="mt-1 line-clamp-2 text-slate-500">{session.user_message}</p>
              </li>
            ))}
            {sessionsQuery.data?.length === 0 && (
              <li className="text-xs text-slate-400">No activity yet.</li>
            )}
          </ul>
        </aside>
      </div>
    </PageLayout>
  );
}