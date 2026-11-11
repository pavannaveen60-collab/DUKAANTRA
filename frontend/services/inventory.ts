
import { apiRequest } from "@/lib/api";
import { getActiveShopId } from "@/lib/shop-context";

function shopPath(resource: string): string {
  return `/api/v1/shops/${getActiveShopId()}/${resource}`;
}

export interface Product {
  id: string;
  shop_id: string;
  name: string;
  sku: string | null;
  category: string | null;
  description: string | null;
  price: number;
  cost_price: number | null;
  is_active: boolean;
  created_at: string;
}

export interface InventoryRecord {
  id: string;
  shop_id: string;
  product_id: string;
  quantity: number;
  low_stock_threshold: number;
  updated_at: string;
}

export interface InventoryMovement {
  id: string;
  shop_id: string;
  product_id: string;
  inventory_id: string;
  user_id: string | null;
  quantity_before: number;
  quantity_change: number;
  quantity_after: number;
  reason: string;
  movement_type: string;
  created_at: string;
}

export interface ProductCreateInput {
  name: string;
  sku?: string | null;
  category?: string | null;
  description?: string | null;
  price: number;
  cost_price?: number | null;
}

export interface ProductUpdateInput {
  name?: string;
  sku?: string | null;
  category?: string | null;
  description?: string | null;
  price?: number;
  cost_price?: number | null;
  is_active?: boolean;
}

export interface InventoryCreateInput {
  product_id: string;
  quantity: number;
  low_stock_threshold: number;
}

export interface InventoryUpdateInput {
  quantity?: number;
  low_stock_threshold?: number;
}

export interface StockAdjustmentInput {
  quantity_change: number;
  reason: string;
}

export async function fetchProducts(includeInactive = false) {
  return apiRequest<Product[]>(
    shopPath(`products/?include_inactive=${includeInactive}`),
  );
}

export async function fetchInventory() {
  return apiRequest<InventoryRecord[]>(shopPath("inventory/"));
}

export async function fetchLowStock() {
  return apiRequest<InventoryRecord[]>(shopPath("inventory/low-stock"));
}

export async function createProduct(data: ProductCreateInput) {
  return apiRequest<Product>(shopPath("products/"), {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateProduct(
  productId: string,
  data: ProductUpdateInput,
) {
  return apiRequest<Product>(shopPath(`products/${productId}`), {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function createInventory(data: InventoryCreateInput) {
  return apiRequest<InventoryRecord>(shopPath("inventory/"), {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateInventory(
  inventoryId: string,
  data: InventoryUpdateInput,
) {
  return apiRequest<InventoryRecord>(
    shopPath(`inventory/${inventoryId}`),
    {
      method: "PATCH",
      body: JSON.stringify(data),
    },
  );
}

export async function adjustStock(
  inventoryId: string,
  data: StockAdjustmentInput,
) {
  return apiRequest<InventoryRecord>(
    shopPath(`inventory/${inventoryId}/adjust`),
    {
      method: "POST",
      body: JSON.stringify(data),
    },
  );
}

export async function fetchMovements(inventoryId: string) {
  return apiRequest<InventoryMovement[]>(
    shopPath(`inventory/${inventoryId}/movements`),
  );
}
