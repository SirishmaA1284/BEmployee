import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";

import { adjustStock, createProduct, listInventory } from "../api/domain";
import { PageLayout } from "../components/PageLayout";

export function InventoryPage() {
  const queryClient = useQueryClient();
  const [lowStockOnly, setLowStockOnly] = useState(false);
  const [form, setForm] = useState({ sku: "", name: "", unit_price: "", reorder_threshold: "0", reorder_quantity: "0" });

  const inventoryQuery = useQuery({
    queryKey: ["inventory", lowStockOnly],
    queryFn: () => listInventory(lowStockOnly),
  });

  const createMutation = useMutation({
    mutationFn: () => createProduct({ ...form, unit_price: form.unit_price, reorder_threshold: Number(form.reorder_threshold), reorder_quantity: Number(form.reorder_quantity) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inventory"] });
      setForm({ sku: "", name: "", unit_price: "", reorder_threshold: "0", reorder_quantity: "0" });
    },
  });

  const adjustMutation = useMutation({
    mutationFn: ({ productId, change }: { productId: string; change: number }) =>
      adjustStock(productId, change),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inventory"] });
      queryClient.invalidateQueries({ queryKey: ["products"] });
    },
  });

  function handleCreate(event: FormEvent) {
    event.preventDefault();
    createMutation.mutate();
  }

  return (
    <PageLayout>
      <h1 className="text-lg font-semibold">Inventory</h1>
      <p className="text-sm text-slate-500">
        Every stock change is logged as a movement — quantities are never edited silently.
      </p>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-semibold">New product</h2>
        <form onSubmit={handleCreate} className="flex flex-wrap gap-2">
          <input
            required
            placeholder="SKU"
            value={form.sku}
            onChange={(e) => setForm({ ...form, sku: e.target.value })}
            className="w-32 rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <input
            required
            placeholder="Name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <input
            required
            type="number"
            min={0}
            step="0.01"
            placeholder="Unit price"
            value={form.unit_price}
            onChange={(e) => setForm({ ...form, unit_price: e.target.value })}
            className="w-28 rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {createMutation.isPending ? "Creating…" : "Create"}
          </button>
        </form>
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Stock levels</h2>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={lowStockOnly}
              onChange={(e) => setLowStockOnly(e.target.checked)}
            />
            Low stock only
          </label>
        </div>

        <table className="w-full rounded-lg border border-slate-200 bg-white text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
              <th className="px-4 py-2">Product</th>
              <th className="px-4 py-2">On hand</th>
              <th className="px-4 py-2">Threshold</th>
              <th className="px-4 py-2">Reorder qty</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Adjust</th>
            </tr>
          </thead>
          <tbody>
            {inventoryQuery.data?.map((item) => (
              <tr key={item.product_id} className="border-b border-slate-100">
                <td className="px-4 py-2">
                  {item.product_name} <span className="text-xs text-slate-400">{item.sku}</span>
                </td>
                <td className="px-4 py-2">{item.quantity_on_hand}</td>
                <td className="px-4 py-2">{item.reorder_threshold}</td>
                <td className="px-4 py-2">{item.reorder_quantity}</td>
                <td className="px-4 py-2">
                  {item.is_low_stock ? (
                    <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
                      Low
                    </span>
                  ) : (
                    <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                      OK
                    </span>
                  )}
                </td>
                <td className="px-4 py-2">
                  <div className="flex gap-1">
                    <button
                      onClick={() => adjustMutation.mutate({ productId: item.product_id, change: 1 })}
                      className="rounded-md border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50"
                    >
                      +1
                    </button>
                    <button
                      onClick={() => adjustMutation.mutate({ productId: item.product_id, change: -1 })}
                      className="rounded-md border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50"
                    >
                      −1
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {inventoryQuery.data?.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-4 text-center text-slate-400">
                  No products yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </PageLayout>
  );
}