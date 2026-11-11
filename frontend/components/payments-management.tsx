"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  CreditCard,
  ExternalLink,
  Loader2,
  RefreshCw,
  ShieldCheck,
  ShoppingBag,
  Trash2,
  Wallet,
} from "lucide-react";
import { ApiError } from "@/lib/api";
import { fetchProducts, fetchInventory, Product, InventoryRecord } from "@/services/inventory";
import { fetchCustomers, Customer } from "@/services/customers";
import { createPaymentCheckout, CheckoutItem } from "@/services/payments";

const money = (value: number) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(value || 0);

function errorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : "Something went wrong.";
}

export default function PaymentsManagement() {
  const [products, setProducts] = useState<Product[]>([]);
  const [inventory, setInventory] = useState<InventoryRecord[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [customerId, setCustomerId] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [approvalUrl, setApprovalUrl] = useState("");
  const [checkout, setCheckout] = useState<{
    inr: string;
    usd: string;
    rate: string;
    provider: string;
    updatedAt: string;
    orderNumber: string;
  } | null>(null);

  const loadData = useCallback(async () => {
    const [productData, inventoryData, customerData] = await Promise.all([
      fetchProducts(),
      fetchInventory(),
      fetchCustomers(),
    ]);
    setProducts(productData.filter((product) => product.is_active));
    setInventory(inventoryData);
    setCustomers(customerData);
  }, []);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError("");
      try {
        await loadData();
      } catch (err) {
        if (active) setError(errorMessage(err));
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [loadData]);

  const inventoryByProduct = useMemo(
    () => new Map(inventory.map((item) => [item.product_id, item])),
    [inventory],
  );

  const selectedItems = useMemo(
    () =>
      products
        .filter((product) => (quantities[product.id] || 0) > 0)
        .map((product) => ({
          product,
          quantity: quantities[product.id],
          subtotal: product.price * quantities[product.id],
        })),
    [products, quantities],
  );

  const total = selectedItems.reduce((sum, item) => sum + item.subtotal, 0);
  const totalUnits = selectedItems.reduce((sum, item) => sum + item.quantity, 0);

  function updateQuantity(product: Product, next: number) {
    const stock = inventoryByProduct.get(product.id)?.quantity ?? 0;
    const safeQuantity = Math.max(0, Math.min(Math.floor(next), stock));
    setQuantities((current) => {
      const updated = { ...current };
      if (safeQuantity === 0) delete updated[product.id];
      else updated[product.id] = safeQuantity;
      return updated;
    });
  }

  async function refresh() {
    setRefreshing(true);
    setError("");
    try {
      await loadData();
      setNotice("Products and stock refreshed.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setRefreshing(false);
    }
  }

  async function startCheckout() {
    if (!selectedItems.length) {
      setError("Add at least one product to continue.");
      return;
    }

    setCheckoutLoading(true);
    setError("");
    setNotice("");
    setCheckout(null);

    try {
      const items: CheckoutItem[] = selectedItems.map(({ product, quantity }) => ({
        product_id: product.id,
        quantity,
      }));

      const result = await createPaymentCheckout({
        customer_id: customerId || null,
        items,
      });

      if (!result.approval_url || !result.payment_id || !result.paypal_order_id) {
        throw new Error("Checkout was created, but PayPal approval details are missing. Check the Payments API response.");
      }

      sessionStorage.setItem(
        "dukaantra_pending_payment",
        JSON.stringify({
          paymentId: result.payment_id,
          paypalOrderId: result.paypal_order_id,
          orderNumber: result.order_number,
        }),
      );

      setApprovalUrl(result.approval_url);
      setCheckout({
        inr: result.source_amount_inr,
        usd: result.amount_usd,
        rate: result.exchange_rate,
        provider: result.exchange_rate_provider,
        updatedAt: result.exchange_rate_updated_at,
        orderNumber: result.order_number,
      });

      setCheckoutLoading(false);
    } catch (err) {
      setError(errorMessage(err));
      setCheckoutLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="dashboard-page">
        <div className="payments-loading"><Loader2 className="animate-spin" /> Loading payment workspace...</div>
      </div>
    );
  }

  return (
    <div className="dashboard-page">
      <div className="dashboard-content">
        <div className="page-heading">
          <div>
            <span className="eyebrow">COMMERCE / TRANSACTIONS</span>
            <h1>Payments</h1>
            <p>Create a customer checkout and securely collect payment through PayPal.</p>
          </div>
          <button className="refresh-button" onClick={refresh} disabled={refreshing}>
            <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
            Refresh data
          </button>
        </div>

        <div className="payments-summary-grid">
          <div className="payments-summary-card">
            <span className="payments-summary-icon"><Wallet size={18} /></span>
            <span>Checkout currency</span>
            <strong>USD</strong>
            <small>PayPal Sandbox processing</small>
          </div>
          <div className="payments-summary-card">
            <span className="payments-summary-icon"><ShoppingBag size={18} /></span>
            <span>Products selected</span>
            <strong>{selectedItems.length}</strong>
            <small>{totalUnits} total units in this checkout</small>
          </div>
          <div className="payments-summary-card">
            <span className="payments-summary-icon"><CreditCard size={18} /></span>
            <span>Checkout total</span>
            <strong>{money(total)}</strong>
            <small>Calculated from current product prices</small>
          </div>
        </div>

        {error && <div className="payments-alert payments-alert-error">{error}</div>}
        {notice && <div className="payments-alert payments-alert-success">{notice}</div>}

        <div className="payments-workspace">
          <section className="payments-panel">
            <div className="payments-panel-heading">
              <div>
                <h2>Build a checkout</h2>
                <p>Select products and quantities for this customer order.</p>
              </div>
              <span className="payments-step">01 / CART</span>
            </div>

            <label className="payments-field">
              <span>Customer <small>Optional</small></span>
              <select value={customerId} onChange={(event) => setCustomerId(event.target.value)}>
                <option value="">Walk-in customer</option>
                {customers.map((customer) => (
                  <option key={customer.id} value={customer.id}>
                    {customer.full_name}{customer.phone ? ` · ${customer.phone}` : ""}
                  </option>
                ))}
              </select>
            </label>

            <div className="payments-product-heading">
              <strong>Available products</strong>
              <span>{products.length} active products</span>
            </div>

            <div className="payments-product-list">
              {products.map((product) => {
                const stock = inventoryByProduct.get(product.id)?.quantity ?? 0;
                const quantity = quantities[product.id] || 0;
                return (
                  <div className="payments-product-row" key={product.id}>
                    <div className="payments-product-avatar">
                      <ShoppingBag size={17} />
                    </div>
                    <div className="payments-product-info">
                      <strong>{product.name}</strong>
                      <span>{product.category || "General"} · {stock} in stock</span>
                    </div>
                    <div className="payments-product-price">{money(product.price)}</div>
                    <div className="payments-quantity">
                      <button
                        type="button"
                        aria-label={`Remove one ${product.name}`}
                        disabled={quantity === 0}
                        onClick={() => updateQuantity(product, quantity - 1)}
                      >−</button>
                      <span>{quantity}</span>
                      <button
                        type="button"
                        aria-label={`Add one ${product.name}`}
                        disabled={stock === 0 || quantity >= stock}
                        onClick={() => updateQuantity(product, quantity + 1)}
                      >+</button>
                    </div>
                  </div>
                );
              })}
              {products.length === 0 && (
                <div className="payments-empty">No active products found. Add products in Inventory first.</div>
              )}
            </div>
          </section>

          <aside className="payments-panel payments-order-panel">
            <div className="payments-panel-heading">
              <div>
                <h2>Order summary</h2>
                <p>Review before creating the PayPal checkout.</p>
              </div>
              <span className="payments-step">02 / REVIEW</span>
            </div>

            <div className="payments-cart-lines">
              {selectedItems.map(({ product, quantity, subtotal }) => (
                <div className="payments-cart-line" key={product.id}>
                  <div>
                    <strong>{product.name}</strong>
                    <span>{quantity} × {money(product.price)}</span>
                  </div>
                  <b>{money(subtotal)}</b>
                  <button
                    type="button"
                    aria-label={`Remove ${product.name}`}
                    onClick={() => updateQuantity(product, 0)}
                  ><Trash2 size={14} /></button>
                </div>
              ))}
              {selectedItems.length === 0 && (
                <div className="payments-cart-empty">Your checkout is empty. Add products to get started.</div>
              )}
            </div>

            <div className="payments-total-line">
              <span>Subtotal (INR)</span>
              <strong>{money(total)}</strong>
            </div>
            <div className="payments-total-line">
              <span>Items</span>
              <strong>{totalUnits}</strong>
            </div>

            <div className="payments-secure-note">
              <ShieldCheck size={17} />
              <span>Stock is checked again by the backend before payment capture. Inventory is deducted only after PayPal confirms payment.</span>
            </div>

            <button
              className="payments-checkout-button"
              onClick={startCheckout}
              disabled={checkoutLoading || selectedItems.length === 0 || !!checkout}
            >
              {checkoutLoading ? <><Loader2 size={16} className="animate-spin" /> Creating checkout...</> : <>Continue to payment <ArrowRight size={16} /></>}
            </button>

            <p className="payments-provider-note">You will review the exchange rate and USD amount before being redirected to PayPal Sandbox.</p>
          </aside>
        </div>

        {checkout && (
          <section className="payments-panel payments-rate-panel">
            <div className="payments-panel-heading">
              <div>
                <h2>Exchange-rate snapshot</h2>
                <p>Locked into the checkout created for order {checkout.orderNumber}.</p>
              </div>
              <span className="payments-step">CHECKOUT CREATED</span>
            </div>
            <div className="payments-rate-grid">
              <div><span>Customer total</span><strong>{money(Number(checkout.inr))}</strong></div>
              <div><span>PayPal amount</span><strong>${Number(checkout.usd).toFixed(2)} USD</strong></div>
              <div><span>Published rate</span><strong>1 INR = ${checkout.rate} USD</strong></div>
            </div>
            <p className="payments-rate-caption">
              Source: {checkout.provider}. Published update: {checkout.updatedAt}.
              This is a published reference rate, not a streaming live market quote.
            </p>
            <button
              className="payments-checkout-button payments-approval-button"
              onClick={() => window.location.assign(approvalUrl)}
              disabled={!approvalUrl}
            >
              Continue to PayPal <ExternalLink size={15} />
            </button>
          </section>
        )}

        <div className="payments-footer-note">
          <CheckCircle2 size={15} />
          PayPal Sandbox is configured for testing. No live customer payment is processed by this screen.
          <ExternalLink size={13} />
        </div>
      </div>
    </div>
  );
}
