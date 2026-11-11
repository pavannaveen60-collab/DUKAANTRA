import { apiRequest } from "@/lib/api";
import { getActiveShopId } from "@/lib/shop-context";

function paymentPath(resource = "") {
  return `/api/v1/shops/${getActiveShopId()}/payments${resource}`;
}

export interface CheckoutItem {
  product_id: string;
  quantity: number;
}

export interface CheckoutInput {
  customer_id?: string | null;
  items: CheckoutItem[];
}

export interface CheckoutResponse {
  order_id: string;
  order_number: string;
  order_status: string;
  payment_id: string;
  payment_status: string;
  source_amount_inr: string;
  amount_usd: string;
  currency: string;
  exchange_rate: string;
  exchange_rate_description: string;
  exchange_rate_provider: string;
  exchange_rate_updated_at: string;
  paypal_order_id: string;
  approval_url: string;
}

export interface CaptureResponse {
  success: boolean;
  message: string;
  payment_id: string;
  order_id?: string;
  order_number?: string;
  capture_id?: string;
  amount_usd?: string;
  currency?: string;
  payment_status?: string;
  order_status?: string;
  inventory_updated?: boolean;
}

export function createPaymentCheckout(data: CheckoutInput) {
  return apiRequest<CheckoutResponse>(paymentPath("/checkout"), {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function capturePayment(paymentId: string) {
  return apiRequest<CaptureResponse>(
    paymentPath(`/${paymentId}/capture`),
    { method: "POST" },
  );
}
