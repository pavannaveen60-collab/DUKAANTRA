import { apiRequest } from "@/lib/api";
import { getActiveShopId } from "@/lib/shop-context";

export interface SalesOverview {
  total_orders: number;
  total_revenue: number;
  units_sold: number;
  average_order_value: number;
}

export interface DailySales {
  date: string;
  orders: number;
  revenue: number;
}

export interface MonthlySales {
  month: string;
  orders: number;
  revenue: number;
}

export interface TopProduct {
  product_id: string;
  product_name: string;
  units_sold: number;
  revenue: number;
}

export async function fetchOverview(): Promise<SalesOverview> {
  return apiRequest(
    `/api/v1/shops/${getActiveShopId()}/analytics/overview`,
  );
}

export async function fetchDailySales(
  days = 7,
): Promise<DailySales[]> {
  return apiRequest(
    `/api/v1/shops/${getActiveShopId()}/analytics/daily?days=${days}`,
  );
}

export async function fetchMonthlySales(
  months = 6,
): Promise<MonthlySales[]> {
  return apiRequest(
    `/api/v1/shops/${getActiveShopId()}/analytics/monthly?months=${months}`,
  );
}

export async function fetchTopProducts(
  limit = 5,
): Promise<TopProduct[]> {
  return apiRequest(
    `/api/v1/shops/${getActiveShopId()}/analytics/top-products?limit=${limit}`,
  );
}