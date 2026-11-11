"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Loader2, AlertCircle } from "lucide-react";
import { capturePayment, CaptureResponse } from "@/services/payments";

export default function PaymentSuccessPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [result, setResult] = useState<CaptureResponse | null>(null);

  useEffect(() => {
    let active = true;

    async function confirmPayment() {
      try {
        const pendingRaw = sessionStorage.getItem("dukaantra_pending_payment");
        if (!pendingRaw) {
          throw new Error("Payment session was not found in this browser. Return to Payments and check the order before retrying.");
        }

        const pending = JSON.parse(pendingRaw) as {
          paymentId: string;
          paypalOrderId: string;
          orderNumber: string;
        };

        const query = new URLSearchParams(window.location.search);
        const paypalToken = query.get("token");

        if (!paypalToken || paypalToken !== pending.paypalOrderId) {
          throw new Error("The PayPal return token does not match the pending checkout. No capture was requested.");
        }

        const response = await capturePayment(pending.paymentId);
        if (!response.success) {
          throw new Error(response.message || "PayPal payment could not be confirmed.");
        }

        if (active) {
          setResult(response);
          sessionStorage.removeItem("dukaantra_pending_payment");
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to confirm payment.");
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    void confirmPayment();
    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="payment-result-screen">
      <section className="payment-result-card">
        {loading ? (
          <>
            <span className="payment-result-icon"><Loader2 className="animate-spin" size={30} /></span>
            <h1>Confirming your payment</h1>
            <p>We are verifying the PayPal transaction and updating your order and inventory. Please keep this page open.</p>
          </>
        ) : error ? (
          <>
            <span className="payment-result-icon payment-result-error"><AlertCircle size={30} /></span>
            <h1>Payment needs verification</h1>
            <p>{error}</p>
            <p className="payment-result-help">Do not create another checkout for the same order until its payment status has been checked.</p>
          </>
        ) : (
          <>
            <span className="payment-result-icon"><CheckCircle2 size={30} /></span>
            <h1>Payment confirmed</h1>
            <p>{result?.message || "Your payment was captured successfully."}</p>
            {result?.order_number && <div className="payment-result-reference">Order {result.order_number}</div>}
            {result?.amount_usd && <div className="payment-result-reference">${result.amount_usd} {result.currency}</div>}
            <p className="payment-result-help">The order is confirmed and inventory has been updated.</p>
          </>
        )}
        <Link className="payment-result-link" href="/payments">Return to Payments</Link>
      </section>
    </main>
  );
}
