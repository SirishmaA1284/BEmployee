import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";

import {
  createPurchaseOrder,
  listProducts,
  listPurchaseOrders,
  listSuppliers,
  receivePurchaseOrder,
  sendPurchaseOrder,
} from "../api/domain";
import { PageLayout } from "../components/PageLayout";

export function PurchaseOrdersPage() {
  const queryClient = useQueryClient();
  const [supplierId, setSupplierId] = useState("");
  const [rows, setRows] = useState<{ product_id: string; quantity: string }[]>([
    { product_id: "", quantity: "1" },
  ]);

  const posQuery = useQuery({ queryKey: ["purchase-orders"], queryFn: listPurchaseOrders });
  const suppliersQuery = useQuery({ queryKey: ["suppliers"], queryFn: listSuppliers });
  const productsQuery = useQuery({ queryKey: ["products"], queryFn: () => listProducts() });

  const createMutation = useMutation({
    mutationFn: () =>
      createPurchaseOrder({
        supplier_id: supplierId,
        items: rows
          .filter((row) => row.product_id)
          .map((row) => ({ product_id: row.product_id, quantity: Number(row.quantity) })),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["purchase-orders"] });
      setSupplierId("");
      setRows([{ product_id: "", quantity: "1" }]);
    },
  });

  const sendMutation = useMutation({
    mutationFn: sendPurchaseOrder,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["purchase-orders"] }),
  });

  const receiveMutation = useMutation({
    mutationFn: receivePurchaseOrder,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["purchase-orders"] });
      queryClient.invalidateQueries({ queryKey: ["inventory"] });
    },
  });

  function handleCreate(event: FormEvent) {
    event.preventDefault();
    createMutation.mutate();
  }

  return (
    <PageLayout>
      <h1 className="text-lg font-semibold">Purchase Orders</h1>
      <p className="text-sm text-slate-500">
        Draft → approve → send → receive. Receiving a PO brings the ordered quantities into inventory.
        Purchase orders above a configured threshold wait in PENDING_APPROVAL for a human decision.
      </p>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-semibold">New purchase order</h2>
        <form onSubmit={handleCreate} className="space-y-3">
          <select
            required
            value={supplierId}
            onChange={(e) => setSupplierId(e.target.value)}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">Select supplier…</option>
            {suppliersQuery.data
              ?.filter((s) => s.is_active)
              .map((supplier) => (
                <option key={supplier.id} value={supplier.id}>
                  {supplier.name}
                </option>
              ))}
          </select>

          <div className="space-y-2">
            {rows.map((row, index) => (
              <div key={index} className="flex gap-2">
                <select
                  value={row.product_id}
                  onChange={(e) => setRows((prev) => {
                    const next = [...prev];
                    next[index] = { ...next[index], product_id: e.target.value };
                    return next;
                  })}
                  className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
                >
                  <option value="">Select product…</option>
                  {productsQuery.data
                    ?.filter((p) => p.is_active)
                    .map((product) => (
                      <option key={product.id} value={product.id}>
                        {product.name} ({product.sku})
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
              onClick={() => setRows((prev) => [...prev, { product_id: "", quantity: "1" }])}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50"
            >
              + Add line
            </button>
          </div>

          <button
            type="submit"
            disabled={createMutation.isPending || !supplierId}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {createMutation.isPending ? "Creating…" : "Create draft"}
          </button>
          {createMutation.isError && <p className="text-sm text-red-600">Could not create the purchase order.</p>}
        </form>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Purchase orders</h2>
        {posQuery.data?.length === 0 && <p className="text-sm text-slate-500">No purchase orders yet.</p>}
        <ul className="space-y-2">
          {posQuery.data?.map((po) => (
            <li key={po.id} className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-medium">{po.supplier_name}</span>
                <div className="flex items-center gap-2">
                  <span className="text-slate-500">{po.total} · {po.status}</span>
                  {po.status === "PENDING_APPROVAL" && (
                    <span className="rounded bg-amber-100 px-2 py-1 text-xs font-medium text-amber-700">
                      Awaiting approval
                    </span>
                  )}
                  {(po.status === "DRAFT" || po.status === "APPROVED") && (
                    <button
                      onClick={() => sendMutation.mutate(po.id)}
                      className="rounded-md border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50"
                    >
                      Send
                    </button>
                  )}
                  {po.status === "SENT" && (
                    <button
                      onClick={() => receiveMutation.mutate(po.id)}
                      className="rounded-md bg-slate-900 px-2 py-1 text-xs font-medium text-white"
                    >
                      Receive
                    </button>
                  )}
                </div>
              </div>
              <p className="mt-1 text-xs text-slate-500">
                {po.items.map((item) => `${item.quantity} x ${item.product_name}`).join(", ")}
              </p>
            </li>
          ))}
        </ul>
      </section>
    </PageLayout>
  );
}