
"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Archive,
  ArrowDown,
  ArrowUp,
  Box,
  Check,
  Clock,
  History,
  Package,
  Plus,
  RefreshCw,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import {
  ApiError,
} from "@/lib/api";
import {
  adjustStock,
  createInventory,
  createProduct,
  fetchInventory,
  fetchMovements,
  fetchProducts,
  InventoryMovement,
  InventoryRecord,
  Product,
  updateProduct,
} from "@/services/inventory";

type ProductForm = {
  name: string;
  sku: string;
  category: string;
  description: string;
  price: string;
  cost_price: string;
  quantity: string;
  low_stock_threshold: string;
};

const emptyForm: ProductForm = {
  name: "",
  sku: "",
  category: "",
  description: "",
  price: "",
  cost_price: "",
  quantity: "0",
  low_stock_threshold: "5",
};

const money = (value: number) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(value || 0);

const integer = (value: number) =>
  new Intl.NumberFormat("en-IN").format(value || 0);

function errorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : "Something went wrong.";
}

function Modal({
  title,
  subtitle,
  onClose,
  children,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="inventory-modal-backdrop" onMouseDown={onClose}>
      <section
        className="inventory-modal"
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header className="inventory-modal-header">
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button
            className="inventory-icon-button"
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
          >
            <X size={19} />
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}

export default function InventoryManagement() {
  const [products, setProducts] = useState<Product[]>([]);
  const [inventory, setInventory] = useState<InventoryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "low" | "out" | "untracked">("all");

  const [showProductForm, setShowProductForm] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [form, setForm] = useState<ProductForm>(emptyForm);
  const [saving, setSaving] = useState(false);

  const [adjusting, setAdjusting] = useState<InventoryRecord | null>(null);
  const [adjustment, setAdjustment] = useState({
    quantity_change: "",
    reason: "Stock replenishment",
  });

  const [historyItem, setHistoryItem] = useState<InventoryRecord | null>(null);
  const [movements, setMovements] = useState<InventoryMovement[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const loadData = useCallback(async () => {
    const [productData, inventoryData] = await Promise.all([
      fetchProducts(true),
      fetchInventory(),
    ]);
    setProducts(productData);
    setInventory(inventoryData);
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

  const activeProducts = useMemo(
    () => products.filter((product) => product.is_active),
    [products],
  );

  const lowStockItems = inventory.filter(
    (item) => item.quantity <= item.low_stock_threshold,
  );

  const outOfStockItems = inventory.filter((item) => item.quantity === 0);

  const trackedProductIds = new Set(inventory.map((item) => item.product_id));

  const filteredProducts = useMemo(() => {
    const query = search.trim().toLowerCase();

    return activeProducts.filter((product) => {
      const stock = inventoryByProduct.get(product.id);

      const matchesSearch =
        !query ||
        product.name.toLowerCase().includes(query) ||
        (product.sku || "").toLowerCase().includes(query) ||
        (product.category || "").toLowerCase().includes(query);

      const matchesFilter =
        filter === "all" ||
        (filter === "low" &&
          !!stock &&
          stock.quantity <= stock.low_stock_threshold &&
          stock.quantity > 0) ||
        (filter === "out" && !!stock && stock.quantity === 0) ||
        (filter === "untracked" && !stock);

      return matchesSearch && matchesFilter;
    });
  }, [activeProducts, inventoryByProduct, search, filter]);

  async function refresh() {
    setRefreshing(true);
    setError("");
    try {
      await loadData();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setRefreshing(false);
    }
  }

  function openCreate() {
    setEditingProduct(null);
    setForm(emptyForm);
    setShowProductForm(true);
    setError("");
    setSuccess("");
  }

  function openEdit(product: Product) {
    const stock = inventoryByProduct.get(product.id);
    setEditingProduct(product);
    setForm({
      name: product.name,
      sku: product.sku || "",
      category: product.category || "",
      description: product.description || "",
      price: String(product.price),
      cost_price: product.cost_price == null ? "" : String(product.cost_price),
      quantity: String(stock?.quantity ?? 0),
      low_stock_threshold: String(stock?.low_stock_threshold ?? 5),
    });
    setShowProductForm(true);
    setError("");
    setSuccess("");
  }

  async function saveProduct(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setSuccess("");

    try {
      const payload = {
        name: form.name.trim(),
        sku: form.sku.trim() || null,
        category: form.category.trim() || null,
        description: form.description.trim() || null,
        price: Number(form.price),
        cost_price: form.cost_price.trim() ? Number(form.cost_price) : null,
      };

      if (!payload.name || !Number.isFinite(payload.price) || payload.price <= 0) {
        throw new Error("Enter a product name and a valid selling price.");
      }

      if (
        payload.cost_price !== null &&
        (!Number.isFinite(payload.cost_price) || payload.cost_price < 0)
      ) {
        throw new Error("Enter a valid cost price.");
      }

      if (editingProduct) {
        await updateProduct(editingProduct.id, payload);

        const existingStock = inventoryByProduct.get(editingProduct.id);
        if (existingStock) {
          const threshold = Number(form.low_stock_threshold);
          if (!Number.isInteger(threshold) || threshold < 0) {
            throw new Error("Low-stock threshold must be a non-negative whole number.");
          }

          const quantity = Number(form.quantity);
          if (!Number.isInteger(quantity) || quantity < 0) {
            throw new Error("Stock quantity must be a non-negative whole number.");
          }

          if (quantity !== existingStock.quantity) {
            throw new Error(
              "Use the Adjust Stock action to change quantity so the movement is recorded.",
            );
          }

          const { updateInventory } = await import("@/services/inventory");
          await updateInventory(existingStock.id, {
            low_stock_threshold: threshold,
          });
        } else {
          const quantity = Number(form.quantity);
          const threshold = Number(form.low_stock_threshold);

          if (
            !Number.isInteger(quantity) ||
            quantity < 0 ||
            !Number.isInteger(threshold) ||
            threshold < 0
          ) {
            throw new Error("Enter valid non-negative whole-number stock values.");
          }

          await createInventory({
            product_id: editingProduct.id,
            quantity,
            low_stock_threshold: threshold,
          });
        }

        setSuccess("Product details updated.");
      } else {
        const created = await createProduct(payload);
        const quantity = Number(form.quantity);
        const threshold = Number(form.low_stock_threshold);

        if (
          !Number.isInteger(quantity) ||
          quantity < 0 ||
          !Number.isInteger(threshold) ||
          threshold < 0
        ) {
          throw new Error(
            "Product was created, but stock was not initialized. Refresh and add its stock record.",
          );
        }

        await createInventory({
          product_id: created.id,
          quantity,
          low_stock_threshold: threshold,
        });

        setSuccess("Product and initial stock created successfully.");
      }

      setShowProductForm(false);
      await loadData();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function archiveProduct(product: Product) {
    const confirmed = window.confirm(
      `Archive "${product.name}"? It will no longer appear in the active product list.`,
    );
    if (!confirmed) return;

    setError("");
    setSuccess("");

    try {
      await updateProduct(product.id, { is_active: false });
      await loadData();
      setSuccess(`${product.name} has been archived.`);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function submitAdjustment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!adjusting) return;

    const change = Number(adjustment.quantity_change);

    if (!Number.isInteger(change) || change === 0) {
      setError("Enter a non-zero whole-number stock adjustment.");
      return;
    }

    if (!adjustment.reason.trim() || adjustment.reason.trim().length < 2) {
      setError("Please provide a reason for this stock adjustment.");
      return;
    }

    setSaving(true);
    setError("");
    setSuccess("");

    try {
      await adjustStock(adjusting.id, {
        quantity_change: change,
        reason: adjustment.reason.trim(),
      });

      setAdjusting(null);
      setAdjustment({
        quantity_change: "",
        reason: "Stock replenishment",
      });
      await loadData();
      setSuccess("Stock adjusted and movement recorded successfully.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function openHistory(item: InventoryRecord) {
    setHistoryItem(item);
    setMovements([]);
    setHistoryLoading(true);
    setError("");

    try {
      const result = await fetchMovements(item.id);
      setMovements(result);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setHistoryLoading(false);
    }
  }

  const productName = (productId: string) =>
    products.find((product) => product.id === productId)?.name || "Unknown product";

  if (loading) {
    return (
      <div className="inventory-loading">
        <RefreshCw className="spin" size={23} />
        <span>Loading your inventory...</span>
      </div>
    );
  }

  return (
    <div className="inventory-page">
      <div className="inventory-heading">
        <div>
          <span className="eyebrow">RETAIL OPERATIONS</span>
          <h1>Inventory</h1>
          <p>Know what you have. Understand what needs attention.</p>
        </div>
        <div className="inventory-heading-actions">
          <button
            className="inventory-secondary-button"
            type="button"
            onClick={refresh}
            disabled={refreshing}
          >
            <RefreshCw size={15} className={refreshing ? "spin" : ""} />
            Refresh
          </button>
          <button
            className="inventory-primary-button"
            type="button"
            onClick={openCreate}
          >
            <Plus size={16} /> Add product
          </button>
        </div>
      </div>

      {error && (
        <div className="inventory-alert inventory-alert-error">
          <AlertTriangle size={17} />
          <span>{error}</span>
          <button type="button" onClick={() => setError("")} aria-label="Dismiss">
            <X size={16} />
          </button>
        </div>
      )}

      {success && (
        <div className="inventory-alert inventory-alert-success">
          <Check size={17} />
          <span>{success}</span>
          <button type="button" onClick={() => setSuccess("")} aria-label="Dismiss">
            <X size={16} />
          </button>
        </div>
      )}

      <section className="inventory-stats">
        <article className="inventory-stat-card">
          <div className="inventory-stat-icon"><Package size={18} /></div>
          <span>Active products</span>
          <strong>{integer(activeProducts.length)}</strong>
          <small>In your catalogue</small>
        </article>
        <article className="inventory-stat-card">
          <div className="inventory-stat-icon"><Box size={18} /></div>
          <span>Tracked items</span>
          <strong>{integer(inventory.length)}</strong>
          <small>With stock records</small>
        </article>
        <article className="inventory-stat-card inventory-stat-warning">
          <div className="inventory-stat-icon"><AlertTriangle size={18} /></div>
          <span>Low stock</span>
          <strong>{integer(lowStockItems.length)}</strong>
          <small>At or below threshold</small>
        </article>
        <article className="inventory-stat-card inventory-stat-danger">
          <div className="inventory-stat-icon"><Archive size={18} /></div>
          <span>Out of stock</span>
          <strong>{integer(outOfStockItems.length)}</strong>
          <small>Tracked items at zero</small>
        </article>
      </section>

      <section className="inventory-workspace">
        <div className="inventory-table-header">
          <div>
            <span className="eyebrow">PRODUCT CATALOGUE</span>
            <h2>Stock overview</h2>
          </div>
          <span className="inventory-result-count">
            {filteredProducts.length} products
          </span>
        </div>

        <div className="inventory-toolbar">
          <div className="inventory-search">
            <Search size={17} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search products, SKU or category..."
              aria-label="Search products"
            />
          </div>
          <div className="inventory-filter">
            <SlidersHorizontal size={15} />
            <select
              value={filter}
              onChange={(event) =>
                setFilter(event.target.value as typeof filter)
              }
              aria-label="Filter inventory"
            >
              <option value="all">All products</option>
              <option value="low">Low stock</option>
              <option value="out">Out of stock</option>
              <option value="untracked">Stock not initialized</option>
            </select>
          </div>
        </div>

        <div className="inventory-table-wrap">
          <table className="inventory-table">
            <thead>
              <tr>
                <th>PRODUCT</th>
                <th>SKU / CATEGORY</th>
                <th>SELLING PRICE</th>
                <th>AVAILABLE STOCK</th>
                <th>STOCK STATUS</th>
                <th className="inventory-actions-heading">ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {filteredProducts.map((product) => {
                const stock = inventoryByProduct.get(product.id);
                const isLow =
                  !!stock && stock.quantity <= stock.low_stock_threshold;
                const isOut = !!stock && stock.quantity === 0;

                return (
                  <tr key={product.id}>
                    <td>
                      <div className="inventory-product-name">
                        <span className="inventory-product-avatar">
                          {product.name.charAt(0).toUpperCase()}
                        </span>
                        <div>
                          <strong>{product.name}</strong>
                          <small>{product.description || "—"}</small>
                        </div>
                      </div>
                    </td>
                    <td>
                      <div className="inventory-secondary-cell">
                        <strong>{product.sku || "No SKU"}</strong>
                        <small>{product.category || "Uncategorised"}</small>
                      </div>
                    </td>
                    <td className="inventory-price">{money(Number(product.price))}</td>
                    <td>
                      {stock ? (
                        <div className="inventory-secondary-cell">
                          <strong>{integer(stock.quantity)} units</strong>
                          <small>Threshold: {stock.low_stock_threshold}</small>
                        </div>
                      ) : (
                        <span className="inventory-muted">Not initialized</span>
                      )}
                    </td>
                    <td>
                      {!stock ? (
                        <span className="inventory-status inventory-status-neutral">
                          Not tracked
                        </span>
                      ) : isOut ? (
                        <span className="inventory-status inventory-status-danger">
                          Out of stock
                        </span>
                      ) : isLow ? (
                        <span className="inventory-status inventory-status-warning">
                          Low stock
                        </span>
                      ) : (
                        <span className="inventory-status inventory-status-good">
                          In stock
                        </span>
                      )}
                    </td>
                    <td>
                      <div className="inventory-row-actions">
                        {stock && (
                          <>
                            <button
                              type="button"
                              title="Adjust stock"
                              onClick={() => {
                                setAdjusting(stock);
                                setAdjustment({
                                  quantity_change: "",
                                  reason: "Stock replenishment",
                                });
                              }}
                            >
                              <SlidersHorizontal size={15} />
                            </button>
                            <button
                              type="button"
                              title="Movement history"
                              onClick={() => void openHistory(stock)}
                            >
                              <History size={15} />
                            </button>
                          </>
                        )}
                        <button
                          type="button"
                          title="Edit product"
                          onClick={() => openEdit(product)}
                        >
                          <Package size={15} />
                        </button>
                        <button
                          type="button"
                          title="Archive product"
                          onClick={() => void archiveProduct(product)}
                        >
                          <Archive size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {filteredProducts.length === 0 && (
            <div className="inventory-empty">
              <Package size={27} />
              <strong>No products found</strong>
              <p>
                {activeProducts.length === 0
                  ? "Add your first product to start managing stock."
                  : "Try changing your search or filter."}
              </p>
              {activeProducts.length === 0 && (
                <button
                  type="button"
                  className="inventory-primary-button"
                  onClick={openCreate}
                >
                  <Plus size={15} /> Add your first product
                </button>
              )}
            </div>
          )}
        </div>
      </section>

      <div className="inventory-footnote">
        <Clock size={14} />
        Stock values are read from your connected inventory records.
      </div>

      {showProductForm && (
        <Modal
          title={editingProduct ? "Edit product" : "Add a product"}
          subtitle={
            editingProduct
              ? "Update product information and stock threshold."
              : "Create a catalogue entry and initialize its stock."
          }
          onClose={() => !saving && setShowProductForm(false)}
        >
          <form className="inventory-form" onSubmit={saveProduct}>
            <div className="inventory-form-grid">
              <label className="inventory-field inventory-field-full">
                Product name *
                <input
                  required
                  minLength={2}
                  maxLength={150}
                  value={form.name}
                  onChange={(event) =>
                    setForm({ ...form, name: event.target.value })
                  }
                  placeholder="e.g. Amul Milk 1L"
                />
              </label>

              <label className="inventory-field">
                SKU
                <input
                  maxLength={100}
                  value={form.sku}
                  onChange={(event) =>
                    setForm({ ...form, sku: event.target.value })
                  }
                  placeholder="Optional SKU"
                />
              </label>

              <label className="inventory-field">
                Category
                <input
                  maxLength={100}
                  value={form.category}
                  onChange={(event) =>
                    setForm({ ...form, category: event.target.value })
                  }
                  placeholder="e.g. Dairy"
                />
              </label>

              <label className="inventory-field">
                Selling price (₹) *
                <input
                  type="number"
                  min="0.01"
                  step="0.01"
                  required
                  value={form.price}
                  onChange={(event) =>
                    setForm({ ...form, price: event.target.value })
                  }
                  placeholder="0.00"
                />
              </label>

              <label className="inventory-field">
                Cost price (₹)
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.cost_price}
                  onChange={(event) =>
                    setForm({ ...form, cost_price: event.target.value })
                  }
                  placeholder="Optional"
                />
              </label>

              <label className="inventory-field inventory-field-full">
                Description
                <textarea
                  maxLength={1000}
                  rows={2}
                  value={form.description}
                  onChange={(event) =>
                    setForm({ ...form, description: event.target.value })
                  }
                  placeholder="Optional product details"
                />
              </label>

              <label className="inventory-field">
                {editingProduct && inventoryByProduct.has(editingProduct.id)
                  ? "Current stock"
                  : "Opening stock"}
                <input
                  type="number"
                  min="0"
                  step="1"
                  required
                  value={form.quantity}
                  disabled={
                    !!editingProduct &&
                    inventoryByProduct.has(editingProduct.id)
                  }
                  onChange={(event) =>
                    setForm({ ...form, quantity: event.target.value })
                  }
                />
                {editingProduct &&
                  inventoryByProduct.has(editingProduct.id) && (
                    <small>Use Adjust Stock to change the quantity.</small>
                  )}
              </label>

              <label className="inventory-field">
                Low-stock threshold
                <input
                  type="number"
                  min="0"
                  step="1"
                  required
                  value={form.low_stock_threshold}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      low_stock_threshold: event.target.value,
                    })
                  }
                />
              </label>
            </div>

            <div className="inventory-modal-actions">
              <button
                type="button"
                className="inventory-secondary-button"
                onClick={() => setShowProductForm(false)}
                disabled={saving}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="inventory-primary-button"
                disabled={saving}
              >
                {saving ? "Saving..." : editingProduct ? "Save changes" : "Create product"}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {adjusting && (
        <Modal
          title="Adjust stock"
          subtitle={`${productName(adjusting.product_id)} · Current stock: ${adjusting.quantity}`}
          onClose={() => !saving && setAdjusting(null)}
        >
          <form className="inventory-form" onSubmit={submitAdjustment}>
            <div className="inventory-adjustment-current">
              <span>Current quantity</span>
              <strong>{integer(adjusting.quantity)} units</strong>
            </div>

            <label className="inventory-field">
              Quantity change *
              <input
                type="number"
                step="1"
                required
                value={adjustment.quantity_change}
                onChange={(event) =>
                  setAdjustment({
                    ...adjustment,
                    quantity_change: event.target.value,
                  })
                }
                placeholder="Example: 10 or -3"
              />
              <small>Use a positive number to add stock and a negative number to reduce it.</small>
            </label>

            <label className="inventory-field">
              Reason *
              <input
                minLength={2}
                maxLength={255}
                required
                value={adjustment.reason}
                onChange={(event) =>
                  setAdjustment({ ...adjustment, reason: event.target.value })
                }
                placeholder="e.g. Supplier delivery, damaged goods"
              />
            </label>

            {adjustment.quantity_change &&
              Number.isInteger(Number(adjustment.quantity_change)) && (
                <div className="inventory-adjustment-preview">
                  <span>Projected stock</span>
                  <strong>
                    {adjusting.quantity + Number(adjustment.quantity_change)} units
                  </strong>
                </div>
              )}

            <div className="inventory-modal-actions">
              <button
                type="button"
                className="inventory-secondary-button"
                onClick={() => setAdjusting(null)}
                disabled={saving}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="inventory-primary-button"
                disabled={saving}
              >
                {saving ? "Updating..." : "Confirm adjustment"}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {historyItem && (
        <Modal
          title="Stock movement history"
          subtitle={productName(historyItem.product_id)}
          onClose={() => setHistoryItem(null)}
        >
          <div className="inventory-history">
            {historyLoading ? (
              <div className="inventory-history-empty">
                <RefreshCw size={20} className="spin" />
                Loading movement history...
              </div>
            ) : movements.length === 0 ? (
              <div className="inventory-history-empty">
                <History size={25} />
                <strong>No movement records</strong>
                <p>No stock movements have been recorded for this item.</p>
              </div>
            ) : (
              movements.map((movement) => (
                <div className="inventory-movement" key={movement.id}>
                  <div
                    className={`inventory-movement-icon ${
                      movement.quantity_change > 0 ? "movement-add" : "movement-remove"
                    }`}
                  >
                    {movement.quantity_change > 0 ? (
                      <ArrowUp size={17} />
                    ) : (
                      <ArrowDown size={17} />
                    )}
                  </div>
                  <div className="inventory-movement-main">
                    <strong>{movement.reason}</strong>
                    <small>
                      {new Date(movement.created_at).toLocaleString("en-IN")}
                    </small>
                    <small>
                      {movement.quantity_before} → {movement.quantity_after} units
                      · {movement.movement_type}
                    </small>
                  </div>
                  <strong
                    className={
                      movement.quantity_change > 0
                        ? "movement-positive"
                        : "movement-negative"
                    }
                  >
                    {movement.quantity_change > 0 ? "+" : ""}
                    {movement.quantity_change}
                  </strong>
                </div>
              ))
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
