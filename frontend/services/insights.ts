import { apiRequest } from "@/lib/api";
import { getActiveShopId } from "@/lib/shop-context";

export interface Overview {
  total_orders: number;
  total_revenue: number;
  units_sold: number;
  average_order_value: number;
}

export interface Period {
  date?: string;
  month?: string;
  orders: number;
  revenue: number;
}

export interface Product {
  product_id: string;
  product_name: string;
  units_sold: number;
  revenue: number;
}

export interface InventoryProduct {
  product_id: string;
  product_name: string;
  status: string;
  current_stock: number | null;
  low_stock_threshold: number | null;
  units_sold_last_28_days: number;
  estimated_daily_demand: number | null;
  estimated_days_of_stock: number | null;
  suggested_reorder_quantity: number | null;
  history_status: string;
}

export interface DemandProduct {
  product_id: string;
  product_name: string;
  status: string;
  history_window_days: number;
  confirmed_sale_days: number;
  units_sold_last_7_days: number;
  units_sold_previous_7_days: number;
  trend: string;
  forecast_period_days: number;
  estimated_units_next_7_days: number | null;
  methodology: string | null;
  limitations: string;
}

export interface Finding {
  id: string;
  agent: string;
  category: string;
  priority: "critical" | "high" | "medium" | "low";
  title: string;
  explanation: string;
  evidence: Record<string, unknown>;
  recommendation: string;
  action_status: "pending_approval" | "completed";
  action_completed: boolean;
  product_id?: string;
  product_name?: string;
}

export interface AgentResult {
  agent: string;
  status: string;
  findings: Finding[];
  [key: string]: unknown;
}

export interface InventoryAgentResult extends AgentResult {
  products_analyzed: number;
  products: InventoryProduct[];
  methodology: string;
}

export interface SalesAgentResult extends AgentResult {
  metrics: {
    confirmed_orders: number;
    confirmed_revenue: number;
    average_order_value: number;
    units_sold: number;
    window_days: number;
  };
  growth_comparison: {
    status: string;
    current_revenue: number;
    previous_revenue: number;
    revenue_change_percent: number | null;
  };
  best_sellers: Product[];
  slow_movers: Array<{
    product_id: string;
    product_name: string;
    units_sold: number;
    revenue: number;
    current_stock: number | null;
  }>;
}

export interface DemandAgentResult extends AgentResult {
  forecast_status: string;
  forecast_period_days: number;
  products_analyzed: number;
  products: DemandProduct[];
  limitations: string;
}

export interface WorkforceReport {
  run_id: string;
  status: string;
  generated_at: string;
  started_at: string;
  completed_at: string;
  agents: WorkforceAgentStatus[];
  agent_results: Record<string, AgentResult>;
  action_plan: {
    total: number;
    by_priority: Record<string, number>;
    items: Finding[];
    note: string;
  };
}

export interface WorkforceAgentStatus {
  agent_type: string;
  name: string;
  status: string;
  execution_completed_at: string | null;
  error?: string | null;
}

export interface WorkforceRun {
  task_id: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  created_at: string | null;
  error: string | null;
  report: WorkforceReport | null;
}

export interface WorkforceStatus {
  shop_id: string;
  status: string;
  latest_run: WorkforceRun | null;
  agents: WorkforceAgentStatus[];
  history: WorkforceRun[];
}

export type InsightsSection =
  | "overview"
  | "daily"
  | "monthly"
  | "products"
  | "workforce";

export interface InsightsData {
  overview: Overview | null;
  daily: Period[] | null;
  monthly: Period[] | null;
  products: Product[] | null;
  workforce: WorkforceStatus | null;
  errors: Partial<Record<InsightsSection, string>>;
}

function failureMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : "This section could not be loaded.";
}

export async function fetchInsights(): Promise<InsightsData> {
  const base = `/api/v1/shops/${getActiveShopId()}`;
  const [
    overviewResult,
    dailyResult,
    monthlyResult,
    productsResult,
    workforceResult,
  ] = await Promise.allSettled([
    apiRequest<Overview>(`${base}/analytics/overview`),
    apiRequest<Period[]>(`${base}/analytics/daily?days=7`),
    apiRequest<Period[]>(`${base}/analytics/monthly?months=6`),
    apiRequest<Product[]>(`${base}/analytics/top-products?limit=5`),
    apiRequest<WorkforceStatus>(`${base}/ai-workforce/`),
  ]);

  const errors: InsightsData["errors"] = {};
  const value = <T>(
    result: PromiseSettledResult<T>,
    section: InsightsSection,
  ): T | null => {
    if (result.status === "fulfilled") return result.value;
    errors[section] = failureMessage(result.reason);
    return null;
  };

  return {
    overview: value(overviewResult, "overview"),
    daily: value(dailyResult, "daily"),
    monthly: value(monthlyResult, "monthly"),
    products: value(productsResult, "products"),
    workforce: value(workforceResult, "workforce"),
    errors,
  };
}

export function runWorkforceAnalysis(): Promise<WorkforceReport> {
  return apiRequest<WorkforceReport>(
    `/api/v1/shops/${getActiveShopId()}/ai-workforce/run`,
    { method: "POST" },
  );
}
