import { apiClient } from "./client";
import type {
  CustomerRead,
  InventoryRead,
  OrderRead,
  ProductRead,
  PurchaseOrderRead,
  SupplierProductRead,
  SupplierRead,
} from "../types/domain";

export async function listProducts(search?: string) {
  const { data } = await apiClient.get<ProductRead[]>("/api/products", {
    params: search ? { search } : undefined,
  });
  return data;
}

export async function createProduct(payload: {
  sku: string;
  name: string;
  unit_price: string;
  cost_price?: string;
  reorder_threshold?: number;
  reorder_quantity?: number;
}) {
  const { data } = await apiClient.post<ProductRead>("/api/products", payload);
  return data;
}

export async function listInventory(lowStockOnly = false) {
  const { data } = await apiClient.get<InventoryRead[]>("/api/inventory", {
    params: lowStockOnly ? { low_stock_only: true } : undefined,
  });
  return data;
}

export async function adjustStock(productId: string, changeQuantity: number, note?: string) {
  const { data } = await apiClient.post<InventoryRead>(
    `/api/inventory/${productId}/adjust`,
    { change_quantity: changeQuantity, note }
  );
  return data;
}

export async function listCustomers() {
  const { data } = await apiClient.get<CustomerRead[]>("/api/customers");
  return data;
}

export async function createCustomer(payload: { name: string; email?: string; phone?: string }) {
  const { data } = await apiClient.post<CustomerRead>("/api/customers", payload);
  return data;
}

export async function listOrders() {
  const { data } = await apiClient.get<OrderRead[]>("/api/orders");
  return data;
}

export async function createOrder(payload: { customer_id: string; items: { product_id: string; quantity: number }[] }) {
  const { data } = await apiClient.post<OrderRead>("/api/orders", payload);
  return data;
}

export async function cancelOrder(orderId: string) {
  const { data } = await apiClient.post<OrderRead>(`/api/orders/${orderId}/cancel`);
  return data;
}

export async function listSuppliers() {
  const { data } = await apiClient.get<SupplierRead[]>("/api/suppliers");
  return data;
}

export async function createSupplier(payload: { name: string; email?: string; phone?: string }) {
  const { data } = await apiClient.post<SupplierRead>("/api/suppliers", payload);
  return data;
}

export async function listSupplierProducts(supplierId: string) {
  const { data } = await apiClient.get<SupplierProductRead[]>(`/api/suppliers/${supplierId}/products`);
  return data;
}

export async function linkSupplierProduct(
  supplierId: string,
  payload: { product_id: string; price: string; lead_time_days: number }
) {
  const { data } = await apiClient.post<SupplierProductRead>(
    `/api/suppliers/${supplierId}/products`,
    payload
  );
  return data;
}

export async function listPurchaseOrders() {
  const { data } = await apiClient.get<PurchaseOrderRead[]>("/api/purchase-orders");
  return data;
}

export async function createPurchaseOrder(payload: {
  supplier_id: string;
  items: { product_id: string; quantity: number }[];
}) {
  const { data } = await apiClient.post<PurchaseOrderRead>("/api/purchase-orders", payload);
  return data;
}

export async function sendPurchaseOrder(poId: string) {
  const { data } = await apiClient.post<PurchaseOrderRead>(`/api/purchase-orders/${poId}/send`);
  return data;
}

export async function receivePurchaseOrder(poId: string) {
  const { data } = await apiClient.post<PurchaseOrderRead>(`/api/purchase-orders/${poId}/receive`);
  return data;
}