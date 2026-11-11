
import { apiRequest } from "@/lib/api";
import type { Product, InventoryRecord } from "@/services/inventory";
import { getActiveShopId } from "@/lib/shop-context";

function shopPath(resource: string) {
  return `/api/v1/shops/${getActiveShopId()}/${resource}`;
}

export interface OrderItem {
  id: string;
  product_id: string;
  quantity: number;
  unit_price: string;
  subtotal: string;
}

export interface Order {
  id: string;
  shop_id: string;
  customer_id: string | null;
  order_number: string;
  status: string;
  total_amount: string;
  created_at: string;
  items: OrderItem[];
}

export interface OrderItemInput {
  product_id: string;
  quantity: number;
}

export interface CreateOrderInput {
  customer_id?: string | null;
  items: OrderItemInput[];
}

export interface Customer {
  id: string;
  shop_id: string;
  full_name: string;
  phone: string | null;
  email: string | null;
  address: string | null;
  created_at: string;
}

export async function fetchOrders(): Promise<Order[]> {
  return apiRequest<Order[]>(shopPath("orders/"));
}

export async function fetchOrder(orderId: string): Promise<Order> {
  return apiRequest<Order>(shopPath(`orders/${orderId}`));
}

export async function createOrder(
  data: CreateOrderInput,
  idempotencyKey: string
): Promise<Order> {
  return apiRequest<Order>(shopPath("orders/"), {
    method: "POST",
    headers: {
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify(data),
  });
}

export async function fetchCustomers(): Promise<Customer[]> {
  return apiRequest<Customer[]>(shopPath("customers/"));
}

export async function fetchOrderProducts(): Promise<Product[]> {
  return apiRequest<Product[]>(shopPath("products/"));
}

export async function fetchOrderInventory(): Promise<InventoryRecord[]> {
  return apiRequest<InventoryRecord[]>(shopPath("inventory/"));
}
