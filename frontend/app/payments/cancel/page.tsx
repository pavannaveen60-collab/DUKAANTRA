"use client";

import Link from "next/link";
import { useEffect } from "react";
import { CircleX } from "lucide-react";

export default function PaymentCancelPage() {
  useEffect(() => {
    // Keep the pending payment reference so the merchant can investigate
    // or retry the same checkout safely.
  }, []);

  return (
    <main className="payment-result-screen">
      <section className="payment-result-card">
        <span className="payment-result-icon payment-result-error"><CircleX size={30} /></span>
        <h1>Checkout cancelled</h1>
        <p>You returned from PayPal without completing the checkout. No inventory has been deducted by this cancellation page.</p>
        <p className="payment-result-help">Check the pending order status before creating another checkout.</p>
        <Link className="payment-result-link" href="/payments">Return to Payments</Link>
      </section>
    </main>
  );
}
