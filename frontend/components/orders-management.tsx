
"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  Search,
  RefreshCw,
  Plus,
  ShoppingCart,
  IndianRupee,
  Package,
  Clock3,
  X,
  ChevronRight,
  UserRound,
  ReceiptText,
  AlertCircle,
  CheckCircle2,
  Minus,
} from "lucide-react";

import {
  fetchOrders,
  fetchOrder,
  createOrder,
  fetchCustomers,
  fetchOrderProducts,
  fetchOrderInventory,
  type Order,
  type Customer,
  type OrderItem,
} from "@/services/orders";

import type { Product, InventoryRecord } from "@/services/inventory";
import { ApiError } from "@/lib/api";
import { getActiveShopId } from "@/lib/shop-context";
import {
  fingerprintOrderRequest,
  readPendingOrderAttempts,
  removePendingOrderAttempt,
  writePendingOrderAttempts,
} from "@/lib/order-idempotency";

function currency(value: number | string) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(Number(value) || 0);
}

function dateTime(value: string) {
  return new Date(value).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function dateOnly(value: string) {
  return new Date(value).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function statusClass(status: string) {
  const value = status.toLowerCase();

  if (value.includes("confirm") || value.includes("complete")) {
    return "order-status success";
  }

  if (value.includes("pending") || value.includes("process")) {
    return "order-status pending";
  }

  if (value.includes("cancel") || value.includes("fail")) {
    return "order-status danger";
  }

  return "order-status neutral";
}

function fetchOrderPageData() {
  return Promise.all([
    fetchOrders(),
    fetchCustomers(),
    fetchOrderProducts(),
    fetchOrderInventory(),
  ]);
}

export default function OrdersManagement() {
  const submissionInFlight = useRef(false);
  const [orders, setOrders] = useState<Order[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [inventory, setInventory] = useState<InventoryRecord[]>([]);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [pendingRetryCount, setPendingRetryCount] = useState(0);
  const [retryStateError, setRetryStateError] = useState("");
  const [retryMode, setRetryMode] = useState(false);

  const [customerId, setCustomerId] = useState("");
  const [orderLines, setOrderLines] = useState<
    { product_id: string; quantity: number }[]
  >([{ product_id: "", quantity: 1 }]);

  const loadData = useCallback(async () => {
    try {
      const [orderData, customerData, productData, inventoryData] =
        await fetchOrderPageData();

      setError("");
      setOrders(orderData);
      setCustomers(customerData);
      setProducts(productData);
      setInventory(inventoryData);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load orders."
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    void fetchOrderPageData()
      .then(([orderData, customerData, productData, inventoryData]) => {
        if (!active) return;
        setError("");
        setOrders(orderData);
        setCustomers(customerData);
        setProducts(productData);
        setInventory(inventoryData);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(
          err instanceof Error ? err.message : "Unable to load orders.",
        );
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
        setRefreshing(false);
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    void Promise.resolve()
      .then(() =>
        readPendingOrderAttempts(getActiveShopId()),
      )
      .then((attempts) => {
        if (!active) return;
        setPendingRetryCount(attempts.length);
        setRetryStateError("");
      })
      .catch((err: unknown) => {
        if (!active) return;
        setRetryStateError(
          err instanceof Error
            ? err.message
            : "Unable to read saved order retry state.",
        );
      });

    return () => {
      active = false;
    };
  }, []);

  const customerMap = useMemo(
    () => new Map(customers.map((customer) => [customer.id, customer])),
    [customers]
  );

  const productMap = useMemo(
    () => new Map(products.map((product) => [product.id, product])),
    [products]
  );

  const inventoryMap = useMemo(
    () => new Map(inventory.map((record) => [record.product_id, record])),
    [inventory]
  );

  const filteredOrders = useMemo(() => {
    const query = search.trim().toLowerCase();

    return orders.filter((order) => {
      const customer = order.customer_id
        ? customerMap.get(order.customer_id)
        : undefined;

      const matchesSearch =
        !query ||
        order.order_number.toLowerCase().includes(query) ||
        (customer?.full_name || "").toLowerCase().includes(query) ||
        (customer?.phone || "").toLowerCase().includes(query);

      const matchesStatus =
        statusFilter === "all" ||
        order.status.toLowerCase() === statusFilter;

      return matchesSearch && matchesStatus;
    });
  }, [orders, search, statusFilter, customerMap]);

  const totalRevenue = orders.reduce(
    (sum, order) => sum + Number(order.total_amount || 0),
    0
  );

  const confirmedOrders = orders.filter((order) =>
    order.status.toLowerCase().includes("confirm")
  ).length;

  const totalUnits = orders.reduce(
    (sum, order) =>
      sum +
      order.items.reduce((itemSum, item) => itemSum + item.quantity, 0),
    0
  );

  async function handleRefresh() {
    setRefreshing(true);
    await loadData();
  }

  async function openOrder(order: Order) {
    setSelectedOrder(order);
    setDetailLoading(true);

    try {
      const fullOrder = await fetchOrder(order.id);
      setSelectedOrder(fullOrder);
    } catch {
      // Keep the order from the list visible if detail retrieval fails.
    } finally {
      setDetailLoading(false);
    }
  }

  function addLine() {
    setOrderLines((current) => [
      ...current,
      { product_id: "", quantity: 1 },
    ]);
  }

  function removeLine(index: number) {
    setOrderLines((current) =>
      current.length === 1
        ? current
        : current.filter((_, i) => i !== index)
    );
  }

  function updateLine(
    index: number,
    field: "product_id" | "quantity",
    value: string | number
  ) {
    setOrderLines((current) =>
      current.map((line, i) =>
        i === index ? { ...line, [field]: value } : line
      )
    );
  }

  const estimatedTotal = orderLines.reduce((sum, line) => {
    const product = productMap.get(line.product_id);
    return sum + (product ? Number(product.price) * line.quantity : 0);
  }, 0);

  function closeCreateOrder() {
    if (submissionInFlight.current) return;
    setRetryMode(false);
    setCreateOpen(false);
  }

  async function handleCreateOrder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submissionInFlight.current) return;
    setCreateError("");
    setSuccessMessage("");

    const validLines = orderLines.filter(
      (line) => line.product_id && line.quantity > 0
    );

    if (validLines.length === 0) {
      setCreateError("Add at least one valid product to the order.");
      return;
    }

    const quantities = new Map<string, number>();

    for (const line of validLines) {
      quantities.set(
        line.product_id,
        (quantities.get(line.product_id) || 0) + line.quantity
      );
    }

    for (const [productId, quantity] of quantities) {
      const product = productMap.get(productId);
      const stock = inventoryMap.get(productId)?.quantity ?? 0;

      if (!product || !product.is_active) {
        setCreateError("One of the selected products is unavailable.");
        return;
      }

      if (quantity > stock) {
        setCreateError(
          `Insufficient stock for ${product.name}. Available: ${stock} units.`
        );
        return;
      }
    }

    setCreating(true);
    submissionInFlight.current = true;
    const requestPayload = {
      customer_id: customerId || null,
      items: [...quantities.entries()]
        .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
        .map(([product_id, quantity]) => ({ product_id, quantity })),
    };

    try {
      const fingerprint = await fingerprintOrderRequest(requestPayload);
      const shopId = getActiveShopId();
      const attempts = readPendingOrderAttempts(shopId);
      const matchingAttempt = retryMode
        ? attempts.find((attempt) => attempt.fingerprint === fingerprint)
        : undefined;
      const idempotencyKey = matchingAttempt?.key ?? crypto.randomUUID();
      const attempt = { fingerprint, key: idempotencyKey };
      const savedAttempts = matchingAttempt
        ? attempts
        : [...attempts, attempt];

      writePendingOrderAttempts(shopId, savedAttempts);
      setPendingRetryCount(savedAttempts.length);

      let created: Order;
      try {
        created = await createOrder(requestPayload, idempotencyKey);
      } catch (err) {
        if (
          err instanceof ApiError &&
          err.status >= 400 &&
          err.status < 500
        ) {
          setRetryMode(false);
          const remaining = removePendingOrderAttempt(
            savedAttempts,
            fingerprint,
            idempotencyKey,
          );
          try {
            writePendingOrderAttempts(shopId, remaining);
            setPendingRetryCount(remaining.length);
          } catch (storageError) {
            setRetryStateError(
              storageError instanceof Error
                ? `The request was rejected, but its saved retry state could not be cleared: ${storageError.message}`
                : "The request was rejected, but its saved retry state could not be cleared.",
            );
          }
        } else {
          setRetryMode(true);
        }
        setCreateError(
          err instanceof Error ? err.message : "Unable to create order.",
        );
        return;
      }

      const remaining = removePendingOrderAttempt(
        savedAttempts,
        fingerprint,
        idempotencyKey,
      );
      try {
        writePendingOrderAttempts(shopId, remaining);
        setPendingRetryCount(remaining.length);
        setRetryStateError("");
      } catch (storageError) {
        setRetryStateError(
          storageError instanceof Error
            ? `Order created, but its saved retry state could not be cleared: ${storageError.message}`
            : "Order created, but its saved retry state could not be cleared.",
        );
      }

      setRetryMode(false);
      setCreateOpen(false);
      setCustomerId("");
      setOrderLines([{ product_id: "", quantity: 1 }]);
      setSuccessMessage(`Order ${created.order_number} created successfully.`);
      await loadData();
      setSelectedOrder(created);
    } catch (err) {
      setCreateError(
        err instanceof Error
          ? `Unable to prepare a retry-safe order: ${err.message}`
          : "Unable to prepare a retry-safe order.",
      );
    } finally {
      submissionInFlight.current = false;
      setCreating(false);
    }
  }

  if (loading) {
    return (
      <div className="orders-loading">
        <RefreshCw size={22} className="spin" />
        <p>Loading your orders...</p>
      </div>
    );
  }

  return (
    <div className="orders-page">
      <div className="orders-heading">
        <div>
          <span className="eyebrow">RETAIL OPERATIONS</span>
          <h1>Orders</h1>
          <p>Track customer purchases and manage incoming orders.</p>
        </div>

        <div className="orders-heading-actions">
          <button
            className="orders-refresh"
            type="button"
            onClick={handleRefresh}
            disabled={refreshing}
          >
            <RefreshCw size={15} className={refreshing ? "spin" : ""} />
            Refresh
          </button>

          <button
            className="orders-create-button"
            type="button"
            onClick={() => {
              setCreateError("");
              setRetryMode(false);
              setCreateOpen(true);
            }}
          >
            <Plus size={17} />
            Create order
          </button>
        </div>
      </div>

      {retryStateError && (
        <div className="orders-error">
          <AlertCircle size={18} />
          <span>{retryStateError}</span>
        </div>
      )}

      {pendingRetryCount > 0 && !createOpen && (
        <div className="orders-error">
          <AlertCircle size={18} />
          <span>
            {pendingRetryCount} order request
            {pendingRetryCount === 1 ? "" : "s"} still need confirmation. Retry
            the exact order to safely reuse its saved key.
          </span>
          <button
            type="button"
            onClick={() => {
              setCreateError("");
              setRetryMode(true);
              setCreateOpen(true);
            }}
          >
            Retry previous order
          </button>
        </div>
      )}

      {error && (
        <div className="orders-error">
          <AlertCircle size={18} />
          <span>{error}</span>
          <button onClick={loadData} type="button">Retry</button>
        </div>
      )}

      {successMessage && (
        <div className="orders-success">
          <CheckCircle2 size={17} />
          {successMessage}
          <button
            type="button"
            onClick={() => setSuccessMessage("")}
            aria-label="Dismiss"
          >
            <X size={15} />
          </button>
        </div>
      )}

      <section className="orders-stats">
        <article className="orders-stat-card">
          <div className="orders-stat-icon green">
            <ShoppingCart size={19} />
          </div>
          <span>Total orders</span>
          <strong>{orders.length}</strong>
          <small>All recorded orders</small>
        </article>

        <article className="orders-stat-card">
          <div className="orders-stat-icon blue">
            <IndianRupee size={19} />
          </div>
          <span>Total order value</span>
          <strong>{currency(totalRevenue)}</strong>
          <small>Sum of recorded order totals</small>
        </article>

        <article className="orders-stat-card">
          <div className="orders-stat-icon orange">
            <Package size={19} />
          </div>
          <span>Units sold</span>
          <strong>{totalUnits}</strong>
          <small>Across all recorded orders</small>
        </article>

        <article className="orders-stat-card">
          <div className="orders-stat-icon purple">
            <CheckCircle2 size={19} />
          </div>
          <span>Confirmed orders</span>
          <strong>{confirmedOrders}</strong>
          <small>Based on current order status</small>
        </article>
      </section>

      <section className="orders-table-panel">
        <div className="orders-table-heading">
          <div>
            <span className="eyebrow">ORDER MANAGEMENT</span>
            <h2>All orders</h2>
            <p>Search and review your store&apos;s order history.</p>
          </div>
          <span className="orders-count">
            {filteredOrders.length} orders
          </span>
        </div>

        <div className="orders-toolbar">
          <div className="orders-search">
            <Search size={17} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search order number, customer or phone..."
              aria-label="Search orders"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch("")}
                aria-label="Clear search"
              >
                <X size={15} />
              </button>
            )}
          </div>

          <select
            className="orders-filter"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            aria-label="Filter by status"
          >
            <option value="all">All statuses</option>
            {Array.from(new Set(orders.map((o) => o.status.toLowerCase()))).map(
              (status) => (
                <option key={status} value={status}>
                  {status.charAt(0).toUpperCase() + status.slice(1)}
                </option>
              )
            )}
          </select>
        </div>

        <div className="orders-table-scroll">
          <table className="orders-table">
            <thead>
              <tr>
                <th>ORDER</th>
                <th>CUSTOMER</th>
                <th>DATE</th>
                <th>ITEMS</th>
                <th>ORDER VALUE</th>
                <th>STATUS</th>
                <th></th>
              </tr>
            </thead>

            <tbody>
              {filteredOrders.map((order) => {
                const customer = order.customer_id
                  ? customerMap.get(order.customer_id)
                  : undefined;

                const itemCount = order.items.reduce(
                  (sum, item) => sum + item.quantity,
                  0
                );

                return (
                  <tr
                    key={order.id}
                    className="orders-table-row"
                    onClick={() => openOrder(order)}
                  >
                    <td>
                      <strong className="order-number">
                        {order.order_number}
                      </strong>
                      <small>{order.id.slice(0, 8)}</small>
                    </td>

                    <td>
                      <div className="order-customer">
                        <div className="order-customer-avatar">
                          {customer?.full_name?.charAt(0).toUpperCase() || "W"}
                        </div>
                        <div>
                          <strong>
                            {customer?.full_name || "Walk-in customer"}
                          </strong>
                          <small>{customer?.phone || "No phone provided"}</small>
                        </div>
                      </div>
                    </td>

                    <td>
                      <span className="order-date">
                        {dateOnly(order.created_at)}
                      </span>
                    </td>

                    <td>{itemCount} units</td>

                    <td>
                      <strong className="order-amount">
                        {currency(order.total_amount)}
                      </strong>
                    </td>

                    <td>
                      <span className={statusClass(order.status)}>
                        {order.status}
                      </span>
                    </td>

                    <td>
                      <button
                        type="button"
                        className="order-view-button"
                        aria-label={`View ${order.order_number}`}
                        onClick={(event) => {
                          event.stopPropagation();
                          openOrder(order);
                        }}
                      >
                        <ChevronRight size={17} />
                      </button>
                    </td>
                  </tr>
                );
              })}

              {filteredOrders.length === 0 && (
                <tr>
                  <td colSpan={7}>
                    <div className="orders-empty">
                      <ShoppingCart size={27} />
                      <strong>No orders found</strong>
                      <span>
                        {search
                          ? "Try changing your search or filters."
                          : "Create your first order to get started."}
                      </span>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="orders-table-footer">
          Showing {filteredOrders.length} of {orders.length} orders
        </div>
      </section>

      {selectedOrder && (
        <div
          className="orders-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setSelectedOrder(null);
            }
          }}
        >
          <section
            className="orders-detail-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="order-detail-title"
          >
            <div className="orders-modal-header">
              <div>
                <span className="eyebrow">ORDER DETAILS</span>
                <h2 id="order-detail-title">
                  {selectedOrder.order_number}
                </h2>
              </div>
              <button
                type="button"
                className="orders-modal-close"
                onClick={() => setSelectedOrder(null)}
                aria-label="Close order details"
              >
                <X size={19} />
              </button>
            </div>

            {detailLoading ? (
              <div className="orders-loading">
                <RefreshCw size={20} className="spin" />
                <p>Loading order details...</p>
              </div>
            ) : (
              <>
                <div className="order-detail-summary">
                  <div>
                    <span>Order status</span>
                    <strong className={statusClass(selectedOrder.status)}>
                      {selectedOrder.status}
                    </strong>
                  </div>
                  <div>
                    <span>Order date</span>
                    <strong>{dateTime(selectedOrder.created_at)}</strong>
                  </div>
                  <div>
                    <span>Total amount</span>
                    <strong className="order-detail-total">
                      {currency(selectedOrder.total_amount)}
                    </strong>
                  </div>
                </div>

                <div className="order-detail-section">
                  <h3>
                    <UserRound size={16} />
                    Customer
                  </h3>
                  {(() => {
                    const customer = selectedOrder.customer_id
                      ? customerMap.get(selectedOrder.customer_id)
                      : undefined;

                    return (
                      <div className="order-detail-customer">
                        <strong>
                          {customer?.full_name || "Walk-in customer"}
                        </strong>
                        <span>{customer?.phone || "No phone provided"}</span>
                        <span>{customer?.email || "No email provided"}</span>
                        <span>{customer?.address || "No address provided"}</span>
                      </div>
                    );
                  })()}
                </div>

                <div className="order-detail-section">
                  <h3>
                    <ReceiptText size={16} />
                    Items in this order
                  </h3>

                  <div className="order-detail-items">
                    {selectedOrder.items.map((item: OrderItem) => {
                      const product = productMap.get(item.product_id);

                      return (
                        <div className="order-detail-item" key={item.id}>
                          <div>
                            <strong>{product?.name || "Product"}</strong>
                            <span>
                              {item.quantity} × {currency(item.unit_price)}
                            </span>
                          </div>
                          <strong>{currency(item.subtotal)}</strong>
                        </div>
                      );
                    })}
                  </div>

                  <div className="order-detail-total-row">
                    <span>Order total</span>
                    <strong>{currency(selectedOrder.total_amount)}</strong>
                  </div>
                </div>

                <div className="order-detail-footnote">
                  <Clock3 size={15} />
                  Order information is retrieved from your business database.
                </div>
              </>
            )}
          </section>
        </div>
      )}

      {createOpen && (
        <div
          className="orders-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !creating) {
              closeCreateOrder();
            }
          }}
        >
          <section
            className="orders-create-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-order-title"
          >
            <div className="orders-modal-header">
              <div>
                <span className="eyebrow">RETAIL OPERATIONS</span>
                <h2 id="create-order-title">Create new order</h2>
                <p>Add customer and products to record a sale.</p>
              </div>
              <button
                type="button"
                className="orders-modal-close"
                onClick={closeCreateOrder}
                aria-label="Close"
              >
                <X size={19} />
              </button>
            </div>

            <form onSubmit={handleCreateOrder}>
              <div className="orders-form-field">
                <label htmlFor="order-customer">Customer</label>
                <select
                  id="order-customer"
                  value={customerId}
                  onChange={(event) => setCustomerId(event.target.value)}
                >
                  <option value="">Walk-in customer</option>
                  {customers.map((customer) => (
                    <option key={customer.id} value={customer.id}>
                      {customer.full_name}
                      {customer.phone ? ` — ${customer.phone}` : ""}
                    </option>
                  ))}
                </select>
                <small>Customer selection is optional.</small>
              </div>

              <div className="orders-form-section-title">
                <div>
                  <strong>Order items</strong>
                  <span>Select products and quantities.</span>
                </div>
                <button
                  type="button"
                  className="orders-add-line"
                  onClick={addLine}
                >
                  <Plus size={14} />
                  Add item
                </button>
              </div>

              <div className="orders-line-list">
                {orderLines.map((line, index) => {
                  const selectedProduct = productMap.get(line.product_id);
                  const available =
                    inventoryMap.get(line.product_id)?.quantity ?? 0;

                  return (
                    <div className="orders-product-line" key={index}>
                      <div className="orders-product-select">
                        <label htmlFor={`order-product-${index}`}>
                          Product
                        </label>
                        <select
                          id={`order-product-${index}`}
                          value={line.product_id}
                          onChange={(event) =>
                            updateLine(index, "product_id", event.target.value)
                          }
                          required
                        >
                          <option value="">Choose product</option>
                          {products
                            .filter((product) => product.is_active)
                            .map((product) => {
                              const stock =
                                inventoryMap.get(product.id)?.quantity ?? 0;

                              return (
                                <option
                                  key={product.id}
                                  value={product.id}
                                  disabled={stock <= 0}
                                >
                                  {product.name} — {currency(product.price)} (
                                  {stock} available)
                                </option>
                              );
                            })}
                        </select>
                        {selectedProduct && (
                          <small>
                            Available stock: {available} units
                          </small>
                        )}
                      </div>

                      <div className="orders-quantity-field">
                        <label htmlFor={`order-quantity-${index}`}>
                          Quantity
                        </label>
                        <input
                          id={`order-quantity-${index}`}
                          type="number"
                          min="1"
                          max={available || 10000}
                          value={line.quantity}
                          onChange={(event) =>
                            updateLine(
                              index,
                              "quantity",
                              Math.max(1, Number(event.target.value))
                            )
                          }
                          required
                        />
                      </div>

                      <button
                        type="button"
                        className="orders-remove-line"
                        disabled={orderLines.length === 1}
                        onClick={() => removeLine(index)}
                        aria-label="Remove item"
                      >
                        <Minus size={15} />
                      </button>
                    </div>
                  );
                })}
              </div>

              <div className="orders-estimate">
                <span>Estimated order total</span>
                <strong>{currency(estimatedTotal)}</strong>
              </div>

              {createError && (
                <div className="orders-form-error">
                  <AlertCircle size={16} />
                  {createError}
                </div>
              )}

              <div className="orders-create-actions">
                <button
                  type="button"
                  className="orders-cancel-button"
                  onClick={closeCreateOrder}
                  disabled={creating}
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  className="orders-submit-button"
                  disabled={creating || products.length === 0}
                >
                  {creating ? (
                    <>
                      <RefreshCw size={15} className="spin" />
                      Creating...
                    </>
                  ) : (
                    <>
                      <Plus size={16} />
                      {retryMode ? "Retry order" : "Create order"}
                    </>
                  )}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}
