export interface ProductRead {
  id: string;
  sku: string;
  name: string;
  description: string | null;
  unit: string;
  unit_price: string;
  cost_price: string | null;
  is_active: boolean;
}

export interface InventoryRead {
  product_id: string;
  sku: string;
  product_name: string;
  quantity_on_hand: number;
  reorder_threshold: number;
  reorder_quantity: number;
  is_low_stock: boolean;
}

export interface CustomerRead {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  address: string | null;
}

export interface SupplierRead {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  is_active: boolean;
}

export interface SupplierProductRead {
  id: string;
  supplier_id: string;
  product_id: string;
  sku: string;
  product_name: string;
  price: string;
  lead_time_days: number;
}

export interface OrderItemRead {
  product_id: string;
  sku: string;
  product_name: string;
  quantity: number;
  unit_price: string;
  line_total: string;
}

export interface OrderRead {
  id: string;
  customer_id: string;
  customer_name: string;
  status: "CONFIRMED" | "CANCELLED";
  subtotal: string;
  tax_amount: string;
  total: string;
  currency: string;
  items: OrderItemRead[];
  invoice_id: string | null;
  invoice_number: string | null;
  created_at: string;
}

export interface PurchaseOrderRead {
  id: string;
  supplier_id: string;
  supplier_name: string;
  status: "DRAFT" | "SENT" | "COMPLETED" | "CANCELLED";
  subtotal: string;
  total: string;
  items: OrderItemRead[];
  created_at: string;
  sent_at: string | null;
  completed_at: string | null;
}