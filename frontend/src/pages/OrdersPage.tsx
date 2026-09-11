import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";

import { createOrder, listCustomers, listOrders, listProducts } from "../api/domain";
import { PageLayout } from "../components/PageLayout";

export function OrdersPage() {
  const queryClient = useQueryClient();
  const [newCustomer, setNewCustomer] = useState(false);
  const [customerId, setCustomerId] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [rows, setRows] = useState<{ product_name: string; product_id: string; quantity: string }[]>([
    { product_name: "", product_id: "", quantity: "1" },
  ]);

  const ordersQuery = useQuery({ queryKey: ["orders"], queryFn: listOrders });
  const customersQuery = useQuery({ queryKey: ["customers"], queryFn: listCustomers });
  const productsQuery = useQuery({ queryKey: ["products"], queryFn: () => listProducts() });

  const createMutation = useMutation({
    mutationFn: () =>
      createOrder({
        customer_id: newCustomer ? undefined : customerId,
        customer: newCustomer
          ? { name: customerName, phone: customerPhone || undefined }
          : undefined,
        items: rows
          .filter((row) => row.product_id)
          .map((row) => ({ product_id: row.product_id, quantity: Number(row.quantity) })),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      queryClient.invalidateQueries({ queryKey: ["customers"] });
      queryClient.invalidateQueries({ queryKey: ["inventory"] });
      setNewCustomer(false);
      setCustomerId("");
      setCustomerName("");
      setCustomerPhone("");
      setRows([{ product_name: "", product_id: "", quantity: "1" }]);
    },
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    createMutation.mutate();
  }

  return (
    <PageLayout>
      <h1 className="text-lg font-semibold">Orders</h1>
      <p className="text-sm text-slate-500">
        Creating an order checks stock, decrements inventory, and generates an invoice in one step.
      </p>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-semibold">New order</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <label className="flex items-center gap-1.5 text-xs font-medium text-slate-600">
            <input
              type="checkbox"
              checked={newCustomer}
              onChange={(e) => setNewCustomer(e.target.checked)}
              className="rounded border-slate-300"
            />
            New customer (not in the list)
          </label>

          {newCustomer ? (
            <div className="flex flex-wrap gap-2">
              <input
                required
                value={customerName}
                onChange={(e) => setCustomerName(e.target.value)}
                placeholder="Customer name"
                className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
              <input
                value={customerPhone}
                onChange={(e) => setCustomerPhone(e.target.value)}
                placeholder="Phone (optional)"
                className="w-48 rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </div>
          ) : (
            <select
              required
              value={customerId}
              onChange={(e) => setCustomerId(e.target.value)}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">Select customer…</option>
              {customersQuery.data?.map((customer) => (
                <option key={customer.id} value={customer.id}>
                  {customer.name}
                </option>
              ))}
            </select>
          )}

          <div className="space-y-2">
            {rows.map((row, index) => (
              <div key={index} className="flex gap-2">
                <select
                  value={row.product_id}
                  onChange={(e) => setRows((prev) => {
                    const next = [...prev];
                    next[index] = { ...next[index], product_id: e.target.value, product_name: e.target.options[e.target.selectedIndex]?.text ?? "" };
                    return next;
                  })}
                  className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
                >
                  <option value="">Select product…</option>
                  {productsQuery.data
                    ?.filter((p) => p.is_active)
                    .map((product) => (
                      <option key={product.id} value={product.id}>
                        {product.name} ({product.sku}) — {product.unit_price}
                      </option>
                    ))}
                </select>
                <input
                  type="number"
                  min={1}
                  value={row.quantity}
                  onChange={(e) => setRows((prev) => {
                    const next = [...prev];
                    next[index] = { ...next[index], quantity: e.target.value };
                    return next;
                  })}
                  className="w-24 rounded-md border border-slate-300 px-3 py-2 text-sm"
                />
                <button
                  type="button"
                  onClick={() => setRows((prev) => prev.filter((_, i) => i !== index))}
                  className="rounded-md border border-slate-300 px-2 text-sm hover:bg-slate-50"
                >
                  Remove
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={() => setRows((prev) => [...prev, { product_name: "", product_id: "", quantity: "1" }])}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50"
            >
              + Add line
            </button>
          </div>

          <button
            type="submit"
            disabled={
              createMutation.isPending || (newCustomer ? !customerName.trim() : !customerId)
            }
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {createMutation.isPending ? "Creating…" : "Create order"}
          </button>
          {createMutation.isError && <p className="text-sm text-red-600">Could not create the order.</p>}
        </form>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Recent orders</h2>
        {ordersQuery.data?.length === 0 && <p className="text-sm text-slate-500">No orders yet.</p>}
        <ul className="space-y-2">
          {ordersQuery.data?.map((order) => (
            <li key={order.id} className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-medium">{order.customer_name}</span>
                <span className="text-slate-500">
                  {order.total} {order.currency} · {order.status} · {order.invoice_number ?? "no invoice"}
                </span>
              </div>
              <p className="mt-1 text-xs text-slate-500">
                {order.items.map((item) => `${item.quantity} x ${item.product_name}`).join(", ")}
              </p>
            </li>
          ))}
        </ul>
      </section>
    </PageLayout>
  );
}