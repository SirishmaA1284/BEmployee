import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";

import {
  createSupplier,
  linkSupplierProduct,
  listProducts,
  listSuppliers,
  listSupplierProducts,
} from "../api/domain";
import { PageLayout } from "../components/PageLayout";

export function SuppliersPage() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [expandedSupplierId, setExpandedSupplierId] = useState<string | null>(null);
  const [linkForm, setLinkForm] = useState({ product_id: "", price: "", lead_time_days: "3" });

  const suppliersQuery = useQuery({ queryKey: ["suppliers"], queryFn: listSuppliers });
  const productsQuery = useQuery({ queryKey: ["products"], queryFn: () => listProducts() });
  const linksQuery = useQuery({
    queryKey: ["supplier-products", expandedSupplierId],
    queryFn: () => listSupplierProducts(expandedSupplierId as string),
    enabled: expandedSupplierId !== null,
  });

  const createMutation = useMutation({
    mutationFn: () => createSupplier({ name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["suppliers"] });
      setName("");
    },
  });

  const linkMutation = useMutation({
    mutationFn: () =>
      linkSupplierProduct(expandedSupplierId as string, {
        product_id: linkForm.product_id,
        price: linkForm.price,
        lead_time_days: Number(linkForm.lead_time_days),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["supplier-products", expandedSupplierId] });
      setLinkForm({ product_id: "", price: "", lead_time_days: "3" });
    },
  });

  function handleCreate(event: FormEvent) {
    event.preventDefault();
    createMutation.mutate();
  }

  return (
    <PageLayout>
      <h1 className="text-lg font-semibold">Suppliers</h1>
      <p className="text-sm text-slate-500">
        Link suppliers to products with their price and lead time — the AI employee uses the same
        data to rank suppliers.
      </p>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-semibold">New supplier</h2>
        <form onSubmit={handleCreate} className="flex gap-2">
          <input
            required
            placeholder="Supplier name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
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
        <h2 className="mb-3 text-lg font-semibold">Suppliers</h2>
        <ul className="space-y-2">
          {suppliersQuery.data?.map((supplier) => (
            <li key={supplier.id} className="rounded-lg border border-slate-200 bg-white">
              <button
                onClick={() => setExpandedSupplierId(expandedSupplierId === supplier.id ? null : supplier.id)}
                className="flex w-full items-center justify-between px-4 py-3 text-left text-sm"
              >
                <span className="font-medium">
                  {supplier.name}
                  {!supplier.is_active && (
                    <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
                      inactive
                    </span>
                  )}
                </span>
                <span className="text-xs text-slate-400">{expandedSupplierId === supplier.id ? "hide" : "products"}</span>
              </button>

              {expandedSupplierId === supplier.id && (
                <div className="border-t border-slate-100 px-4 py-3">
                  <ul className="mb-3 space-y-1 text-xs text-slate-600">
                    {linksQuery.data?.map((link) => (
                      <li key={link.id} className="flex justify-between">
                        <span>{link.product_name} ({link.sku})</span>
                        <span>
                          {link.price} · lead {link.lead_time_days}d
                        </span>
                      </li>
                    ))}
                    {linksQuery.data?.length === 0 && (
                      <li className="text-slate-400">No products linked yet.</li>
                    )}
                  </ul>
                  <div className="flex flex-wrap gap-2">
                    <select
                      value={linkForm.product_id}
                      onChange={(e) => setLinkForm({ ...linkForm, product_id: e.target.value })}
                      className="rounded-md border border-slate-300 px-2 py-1.5 text-xs"
                    >
                      <option value="">Product…</option>
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
                      min={0}
                      step="0.01"
                      placeholder="Price"
                      value={linkForm.price}
                      onChange={(e) => setLinkForm({ ...linkForm, price: e.target.value })}
                      className="w-24 rounded-md border border-slate-300 px-2 py-1.5 text-xs"
                    />
                    <input
                      type="number"
                      min={0}
                      placeholder="Lead days"
                      value={linkForm.lead_time_days}
                      onChange={(e) => setLinkForm({ ...linkForm, lead_time_days: e.target.value })}
                      className="w-24 rounded-md border border-slate-300 px-2 py-1.5 text-xs"
                    />
                    <button
                      onClick={() => linkMutation.mutate()}
                      disabled={!linkForm.product_id || !linkForm.price}
                      className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
                    >
                      Link product
                    </button>
                  </div>
                </div>
              )}
            </li>
          ))}
          {suppliersQuery.data?.length === 0 && <p className="text-sm text-slate-500">No suppliers yet.</p>}
        </ul>
      </section>
    </PageLayout>
  );
}