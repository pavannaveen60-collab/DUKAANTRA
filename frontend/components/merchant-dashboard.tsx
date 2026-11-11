
"use client";

import {
  useCallback,
  useEffect,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  Package,
  ShoppingCart,
  Users,
  ChartNoAxesCombined,
  CreditCard,
  BrainCircuit,
  Settings,
  HelpCircle,
  LogOut,
  RefreshCw,
  Menu,
  X,
  Store,
  TrendingUp,
  IndianRupee,
  Boxes,
  ArrowUpRight,
  AlertCircle,
} from "lucide-react";

import {
  login,
  getToken,
  clearToken,
  apiRequest,
} from "@/lib/api";
import {
  clearActiveShopId,
  getActiveShopId,
  setActiveShopId,
} from "@/lib/shop-context";
import { fetchMyShops } from "@/services/shops";

type Overview = {
  total_orders: number;
  total_revenue: number;
  units_sold: number;
  average_order_value: number;
};

type DailySale = {
  date: string;
  orders: number;
  revenue: number;
};

type TopProduct = {
  product_id: string;
  product_name: string;
  units_sold: number;
  revenue: number;
};

type MerchantDashboardProps = {
  children?: ReactNode;
};

const navigation = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Inventory", href: "/inventory", icon: Package },
  { label: "Orders", href: "/orders", icon: ShoppingCart },
  { label: "Customers", href: "/customers", icon: Users },
  { label: "Insights", href: "/insights", icon: ChartNoAxesCombined },
  { label: "Payments", href: "/payments", icon: CreditCard },
  { label: "DUKAANTRA AI", href: "/ai", icon: BrainCircuit },
];

function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value || 0);
}

function LoginScreen({
  onLogin,
}: {
  onLogin: (email: string, password: string) => Promise<void>;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      await onLogin(email, password);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to sign in. Please try again."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-screen">
      <div className="login-card">
        <div className="login-brand">
          <div className="brand-mark">
            <Store size={24} />
          </div>
          <span>DUKAANTRA</span>
        </div>

        <div className="login-heading">
          <span className="eyebrow">MERCHANT WORKSPACE</span>
          <h1>Welcome back.</h1>
          <p>Sign in to manage your business intelligence.</p>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          <label htmlFor="merchant-email">Email address</label>
          <input
            id="merchant-email"
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />

          <label htmlFor="merchant-password">Password</label>
          <input
            id="merchant-password"
            type="password"
            autoComplete="current-password"
            placeholder="Enter your password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />

          {error && <div className="login-error" role="alert">{error}</div>}

          <button type="submit" disabled={loading}>
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <p className="login-footer">
          Secure access to your DUKAANTRA workspace
        </p>
        <p className="onboarding-switch">
          New to DUKAANTRA? <Link href="/register">Create an account</Link>
        </p>
      </div>
    </main>
  );
}

function DashboardContent({
  overview,
  dailySales,
  products,
  onRefresh,
  refreshing,
}: {
  overview: Overview;
  dailySales: DailySale[];
  products: TopProduct[];
  onRefresh: () => void;
  refreshing: boolean;
}) {
  const maxRevenue = Math.max(
    ...dailySales.map((item) => item.revenue),
    1
  );

  return (
    <div className="dashboard-content">
      <div className="page-heading">
        <div>
          <span className="eyebrow">BUSINESS OVERVIEW</span>
          <h1>Good business starts with clarity.</h1>
          <p>Here is what is happening in your store.</p>
        </div>

        <button
          className="refresh-button"
          onClick={onRefresh}
          disabled={refreshing}
          type="button"
        >
          <RefreshCw size={16} className={refreshing ? "spin" : ""} />
          Refresh
        </button>
      </div>

      <section className="stats-grid">
        <article className="stat-card">
          <div className="stat-card-top">
            <span>Total revenue</span>
            <div className="stat-icon green">
              <IndianRupee size={19} />
            </div>
          </div>
          <strong>{formatCurrency(overview.total_revenue)}</strong>
          <small>Revenue recorded from orders</small>
        </article>

        <article className="stat-card">
          <div className="stat-card-top">
            <span>Total orders</span>
            <div className="stat-icon blue">
              <ShoppingCart size={19} />
            </div>
          </div>
          <strong>{overview.total_orders}</strong>
          <small>Orders recorded in your store</small>
        </article>

        <article className="stat-card">
          <div className="stat-card-top">
            <span>Units sold</span>
            <div className="stat-icon orange">
              <Boxes size={19} />
            </div>
          </div>
          <strong>{overview.units_sold}</strong>
          <small>Total items sold</small>
        </article>

        <article className="stat-card">
          <div className="stat-card-top">
            <span>Average order value</span>
            <div className="stat-icon purple">
              <TrendingUp size={19} />
            </div>
          </div>
          <strong>{formatCurrency(overview.average_order_value)}</strong>
          <small>Average value per order</small>
        </article>
      </section>

      <section className="dashboard-grid">
        <article className="dashboard-panel sales-panel">
          <div className="panel-heading">
            <div>
              <h2>Sales activity</h2>
              <p>Daily revenue over the last 7 days</p>
            </div>
            <span className="panel-icon">
              <ChartNoAxesCombined size={19} />
            </span>
          </div>

          {dailySales.length === 0 ? (
            <div className="empty-state">
              No sales activity available yet.
            </div>
          ) : (
            <div className="sales-chart">
              {dailySales.map((item) => (
                <div className="sales-bar-column" key={item.date}>
                  <span className="sales-bar-value">
                    {item.revenue > 0
                      ? formatCurrency(item.revenue)
                      : "₹0"}
                  </span>
                  <div className="sales-bar-track">
                    <div
                      className="sales-bar"
                      style={{
                        height: `${Math.max(
                          (item.revenue / maxRevenue) * 100,
                          item.revenue > 0 ? 5 : 0
                        )}%`,
                      }}
                    />
                  </div>
                  <span className="sales-bar-label">
                    {new Date(item.date).toLocaleDateString("en-IN", {
                      weekday: "short",
                    })}
                  </span>
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="dashboard-panel products-panel">
          <div className="panel-heading">
            <div>
              <h2>Top selling products</h2>
              <p>Your best performing products</p>
            </div>
            <Package size={19} />
          </div>

          {products.length === 0 ? (
            <div className="empty-state">
              No product sales available yet.
            </div>
          ) : (
            <div className="top-products-list">
              {products.map((product, index) => (
                <div className="top-product-row" key={product.product_id}>
                  <div className="product-rank">{index + 1}</div>
                  <div className="product-details">
                    <strong>{product.product_name}</strong>
                    <span>{product.units_sold} units sold</span>
                  </div>
                  <div className="product-revenue">
                    {formatCurrency(product.revenue)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </article>
      </section>

      <section className="dashboard-bottom-note">
        <div className="note-icon">
          <TrendingUp size={19} />
        </div>
        <div>
          <strong>Your business, in one place.</strong>
          <p>
            Use Inventory to manage products and stock, and Insights to explore
            your business performance.
          </p>
        </div>
        <ArrowUpRight size={18} />
      </section>
    </div>
  );
}

export default function MerchantDashboard({
  children,
}: MerchantDashboardProps) {
  const router = useRouter();
  const pathname = usePathname();

  const [authenticated, setAuthenticated] = useState(false);
  const [authChecking, setAuthChecking] = useState(true);
  const [redirecting, setRedirecting] = useState(false);
  const [shopId, setShopId] = useState("");
  const [shopCount, setShopCount] = useState(0);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const [overview, setOverview] = useState<Overview | null>(null);
  const [dailySales, setDailySales] = useState<DailySale[]>([]);
  const [products, setProducts] = useState<TopProduct[]>([]);

  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [dashboardError, setDashboardError] = useState("");

  const loadDashboard = useCallback(async () => {
    if (!shopId) {
      setDashboardError("Select a shop to load its dashboard.");
      return;
    }

    setLoading(true);
    setDashboardError("");

    try {
      const [overviewData, dailyData, productsData] = await Promise.all([
        apiRequest<Overview>(
          `/api/v1/shops/${shopId}/analytics/overview`
        ),
        apiRequest<DailySale[]>(
          `/api/v1/shops/${shopId}/analytics/daily?days=7`
        ),
        apiRequest<TopProduct[]>(
          `/api/v1/shops/${shopId}/analytics/top-products?limit=5`
        ),
      ]);

      setOverview(overviewData);
      setDailySales(dailyData);
      setProducts(productsData);
    } catch (error) {
      setDashboardError(
        error instanceof Error
          ? error.message
          : "Unable to load dashboard data."
      );
    } finally {
      setLoading(false);
    }
  }, [shopId]);

  useEffect(() => {
    let active = true;

    async function checkAuthentication() {
      try {
        const token = getToken();

        if (!token) {
          if (active) setAuthenticated(false);
          return;
        }

        await apiRequest("/api/v1/auth/me");
        const shops = await fetchMyShops();
        if (!active) return;
        setShopCount(shops.length);

        if (shops.length === 0) {
          setRedirecting(true);
          router.replace("/onboarding/shop");
          return;
        }

        let selectedShopId = "";
        try {
          selectedShopId = getActiveShopId();
        } catch {
          // A first login may not have a stored shop selection.
        }

        const selectedShop = shops.find((shop) => shop.id === selectedShopId);
        if (selectedShop) {
          setShopId(selectedShop.id);
          setAuthenticated(true);
        } else if (shops.length === 1) {
          setActiveShopId(shops[0].id);
          setShopId(shops[0].id);
          setAuthenticated(true);
        } else {
          clearActiveShopId();
          setRedirecting(true);
          router.replace("/shops/select");
        }
      } catch {
        clearToken();
        clearActiveShopId();
        if (active) setAuthenticated(false);
      } finally {
        if (active) setAuthChecking(false);
      }
    }

    checkAuthentication();

    return () => {
      active = false;
    };
  }, [router]);

  useEffect(() => {
    if (authenticated && !children) {
      void Promise.resolve().then(loadDashboard);
    }
  }, [authenticated, children, loadDashboard, shopId]);

  async function handleLogin(email: string, password: string) {
    await login(email, password);
    const shops = await fetchMyShops();
    setShopCount(shops.length);

    if (shops.length === 0) {
      setRedirecting(true);
      router.replace("/onboarding/shop");
      return;
    }

    if (shops.length > 1) {
      let selectedShopId = "";
      try {
        selectedShopId = getActiveShopId();
      } catch {
        // Ask the merchant to choose when there is no valid current selection.
      }
      const selectedShop = shops.find((shop) => shop.id === selectedShopId);
      if (!selectedShop) {
        clearActiveShopId();
        setRedirecting(true);
        router.replace("/shops/select");
        return;
      }
      setShopId(selectedShop.id);
    } else {
      setActiveShopId(shops[0].id);
      setShopId(shops[0].id);
    }

    setAuthenticated(true);
  }

  function handleLogout() {
    clearToken();
    clearActiveShopId();
    setAuthenticated(false);
    setRedirecting(false);
    setShopId("");
    setShopCount(0);
    setOverview(null);
    setDailySales([]);
    setProducts([]);
    router.push("/dashboard");
  }

  async function handleRefresh() {
    setRefreshing(true);
    await loadDashboard();
    setRefreshing(false);
  }

  if (authChecking || redirecting) {
    return (
      <div className="dashboard-loading">
        <RefreshCw size={22} className="spin" />
        <p>Checking your secure workspace...</p>
      </div>
    );
  }

  if (!authenticated) {
    return <LoginScreen onLogin={handleLogin} />;
  }

  return (
    <div className="dashboard-shell">
      {mobileMenuOpen && (
        <button
          className="sidebar-overlay"
          aria-label="Close navigation"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      <aside className={`dashboard-sidebar ${mobileMenuOpen ? "mobile-open" : ""}`}>
        <div className="sidebar-brand">
          <div className="brand-mark">
            <Store size={21} />
          </div>
          <div>
            <strong>DUKAANTRA</strong>
            <span>MERCHANT WORKSPACE</span>
          </div>

          <button
            className="mobile-close"
            aria-label="Close menu"
            onClick={() => setMobileMenuOpen(false)}
          >
            <X size={19} />
          </button>
        </div>

        <div className="sidebar-section-label">WORKSPACE</div>

        <nav className="sidebar-navigation">
          {navigation.map((item) => {
            const Icon = item.icon;
            const active =
              pathname === item.href ||
              (item.href !== "/dashboard" &&
                pathname.startsWith(`${item.href}/`));

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`nav-item ${active ? "active" : ""}`}
                onClick={() => setMobileMenuOpen(false)}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="sidebar-section-label sidebar-tools-label">
          PREFERENCES
        </div>

        <nav className="sidebar-navigation">
          <div className="nav-item disabled">
            <Settings size={18} />
            <span>Settings</span>
          </div>
          <div className="nav-item disabled">
            <HelpCircle size={18} />
            <span>Help & support</span>
          </div>
        </nav>

        <div className="sidebar-bottom">
          <div className="sidebar-status">
            <span className="status-dot" />
            <span>Workspace connected</span>
          </div>

          <button className="logout-button" onClick={handleLogout}>
            <LogOut size={17} />
            <span>Sign out</span>
          </button>

          <div className="sidebar-version">DUKAANTRA · MERCHANT EDITION</div>
        </div>
      </aside>

      <div className="dashboard-main">
        <header className="dashboard-topbar">
          <button
            className="mobile-menu-button"
            aria-label="Open navigation"
            onClick={() => setMobileMenuOpen(true)}
          >
            <Menu size={21} />
          </button>

          <div className="topbar-breadcrumb">
            <span>Workspace</span>
            <span className="breadcrumb-divider">/</span>
            <strong>
              {navigation.find((item) => item.href === pathname)?.label ||
                (pathname.startsWith("/inventory") ? "Inventory" : "Dashboard")}
            </strong>
          </div>

          <div className="topbar-right">
            {shopCount > 1 && (
              <button
                className="shop-switch-button"
                onClick={() => router.push("/shops/select")}
              >
                Switch shop
              </button>
            )}
            <span className="topbar-status">
              <span className="status-dot" />
              Live workspace
            </span>
            <div className="merchant-avatar">M</div>
          </div>
        </header>

        <main className="dashboard-page">
          {children ? (
            children
          ) : loading && !overview ? (
            <div className="dashboard-loading">
              <RefreshCw size={22} className="spin" />
              <p>Connecting to your business data...</p>
            </div>
          ) : dashboardError ? (
            <div className="dashboard-error">
              <AlertCircle size={20} />
              <div>
                <strong>Unable to load your dashboard</strong>
                <p>{dashboardError}</p>
                <button onClick={loadDashboard}>Try again</button>
              </div>
            </div>
          ) : overview ? (
            <DashboardContent
              overview={overview}
              dailySales={dailySales}
              products={products}
              onRefresh={handleRefresh}
              refreshing={refreshing}
            />
          ) : (
            <div className="dashboard-loading">
              <RefreshCw size={22} className="spin" />
              <p>Loading your business data...</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
