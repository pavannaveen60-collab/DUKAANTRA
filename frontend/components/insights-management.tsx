"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  RefreshCw, IndianRupee, ShoppingCart, Boxes,
  TrendingUp, BrainCircuit, AlertTriangle,
  Package, Activity, Play, Clock3
} from "lucide-react";
import { fetchInsights, runWorkforceAnalysis } from "@/services/insights";
import type {
  DemandProduct,
  DemandAgentResult,
  Finding,
  InventoryAgentResult,
  InsightsData,
  Period,
  Product,
  SalesAgentResult,
} from "@/services/insights";

const money = (value: number) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(Number(value) || 0);

const dateLabel = (value?: string) => {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
};

const displayEvidence = (value: unknown) =>
  Array.isArray(value)
    ? value.map((item) => typeof item === "object" ? JSON.stringify(item) : String(item)).join(", ")
    : typeof value === "object" && value !== null
      ? JSON.stringify(value)
      : String(value ?? "—");

export default function InsightsManagement() {
  const [data, setData] = useState<InsightsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [running, setRunning] = useState(false);
  const [analysisError, setAnalysisError] = useState("");
  const [error, setError] = useState("");
  const analysisInFlight = useRef(false);

  const load = useCallback(async (refresh = false) => {
    if (refresh) setRefreshing(true);
    else setLoading(true);

    setError("");

    try {
      setData(await fetchInsights());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load insights.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const runAnalysis = useCallback(async () => {
    if (analysisInFlight.current) return;
    analysisInFlight.current = true;
    setRunning(true);
    setAnalysisError("");
    document.getElementById("ai-workforce")?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });

    try {
      await runWorkforceAnalysis();
      await load(true);
    } catch (cause) {
      const message = cause instanceof Error
        ? cause.message
        : "The AI workforce analysis could not be completed.";
      await load(true);
      setAnalysisError(message);
    } finally {
      analysisInFlight.current = false;
      setRunning(false);
    }
  }, [load]);

  useEffect(() => {
    let active = true;

    void Promise.resolve()
      .then(() => {
        return fetchInsights();
      })
      .then((result) => {
        if (active) setData(result);
      })
      .catch((cause: unknown) => {
        if (active) {
          setError(cause instanceof Error ? cause.message : "Unable to load insights.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return (
      <main className="insights-page">
        <div className="insights-loading">
          <RefreshCw className="spin" size={25} />
          <h2>Loading your business insights...</h2>
          <p>Fetching sales data and workforce status.</p>
        </div>
      </main>
    );
  }

  if (error && !data) {
    return (
      <main className="insights-page">
        <div className="insights-error">
          <AlertTriangle size={25} />
          <h2>Insights could not be loaded</h2>
          <p>{error}</p>
          <button onClick={() => void load()}>Try again</button>
        </div>
      </main>
    );
  }

  if (!data) return null;

  const latestRun = data.workforce?.latest_run;
  const completedRun = data.workforce?.history.find((run) => run.status === "completed");
  const ai = completedRun?.report;
  const inventory = ai?.agent_results.inventory as InventoryAgentResult | undefined;
  const sales = ai?.agent_results.sales as SalesAgentResult | undefined;
  const demand = ai?.agent_results.demand as DemandAgentResult | undefined;
  const demandProducts = Array.isArray(demand?.products)
    ? demand.products as DemandProduct[]
    : [];
  const recommendations = ai?.action_plan.items || [];
  const agents = data.workforce?.agents || [];
  const daily = data.daily || [];
  const monthly = data.monthly || [];
  const products = data.products || [];
  const overview = data.overview;
  const maxDaily = Math.max(...daily.map((item) => Number(item.revenue) || 0), 1);
  const maxMonthly = Math.max(...monthly.map((item) => Number(item.revenue) || 0), 1);
  const maxProduct = Math.max(...products.map((product) => product.units_sold), 1);

  return (
    <main className="insights-page">
      <header className="insights-heading">
        <div>
          <span className="eyebrow">BUSINESS INTELLIGENCE</span>
          <h1>Insights that move your business forward.</h1>
          <p>Understand performance, anticipate demand and make informed decisions.</p>
        </div>
        <div className="insights-actions">
          <button
            className="refresh-button run-analysis-button"
            onClick={() => void runAnalysis()}
            disabled={running}
          >
            {running ? (
              <RefreshCw size={16} className="spin" />
            ) : (
              <Play size={16} />
            )}
            {running ? "Running Analysis..." : "Run Analysis"}
          </button>
          <button
            className="refresh-button"
            onClick={() => void load(true)}
            disabled={refreshing || running}
            aria-label="Refresh insights and analysis status"
          >
            <RefreshCw size={16} className={refreshing ? "spin" : ""} />
            Refresh
          </button>
        </div>
      </header>

      {error && <p className="insight-inline-error">{error}</p>}

      <section className="insight-stats-grid">
        {[
          { label: "Total revenue", value: overview ? money(overview.total_revenue) : "—", detail: "Confirmed-order revenue", icon: IndianRupee, tone: "green" },
          { label: "Total orders", value: overview?.total_orders ?? "—", detail: "Confirmed orders", icon: ShoppingCart, tone: "blue" },
          { label: "Units sold", value: overview?.units_sold ?? "—", detail: "Units in confirmed orders", icon: Boxes, tone: "orange" },
          { label: "Average order value", value: overview ? money(overview.average_order_value) : "—", detail: "Revenue per confirmed order", icon: TrendingUp, tone: "purple" },
        ].map((item) => (
          <article className="insight-stat" key={item.label}>
            <div className="insight-stat-top">
              <span>{item.label}</span>
              <span className={`insight-stat-icon ${item.tone}`}>
                <item.icon size={19} />
              </span>
            </div>
            <strong>{item.value}</strong>
            <small>{item.detail}</small>
          </article>
        ))}
      </section>
      {data.errors.overview && (
        <div className="insight-empty" role="alert">
          Sales overview could not be loaded: {data.errors.overview}
        </div>
      )}

      <div className="insight-section-title">
        <div>
          <span className="eyebrow">PERFORMANCE</span>
          <h2>Sales analytics</h2>
        </div>
        <span className="insight-live-label"><Activity size={14} /> Live business data</span>
      </div>

      <section className="insight-charts-grid">
        {[
          { title: "Daily sales", subtitle: "Last 7 days", items: daily, max: maxDaily, key: "date" as const, section: "daily" as const },
          { title: "Monthly performance", subtitle: "Last 6 months", items: monthly, max: maxMonthly, key: "month" as const, section: "monthly" as const },
        ].map((chart) => (
          <article className="insight-panel" key={chart.title}>
            <div className="insight-panel-heading">
              <div><h2>{chart.title}</h2><p>{chart.subtitle}</p></div>
              <TrendingUp size={20} />
            </div>
            {data.errors[chart.section] ? (
              <div className="insight-empty" role="alert">
                This chart could not be loaded: {data.errors[chart.section]}
              </div>
            ) : chart.items.length === 0 ? (
              <div className="insight-empty">No sales data available.</div>
            ) : (
              <div className="insight-chart">
                {chart.items.map((item: Period, i: number) => (
                  <div className="insight-chart-column" key={item[chart.key] || i}>
                    <span className="insight-chart-value">{money(item.revenue)}</span>
                    <div className="insight-chart-track">
                      <div className="insight-chart-bar" style={{
                        height: `${item.revenue ? Math.max(item.revenue / chart.max * 100, 5) : 0}%`
                      }} />
                    </div>
                    <span className="insight-chart-label">
                      {chart.key === "date" ? dateLabel(item.date) : item.month?.slice(5)}
                    </span>
                    <small>{item.orders} orders</small>
                  </div>
                ))}
              </div>
            )}
          </article>
        ))}
      </section>

      <section className="insight-lower-grid">
        <article className="insight-panel">
          <div className="insight-panel-heading">
            <div><h2>Top-selling products</h2><p>Ranked by units sold</p></div>
            <Package size={20} />
          </div>
          {data.errors.products ? (
            <div className="insight-empty" role="alert">
              Product sales could not be loaded: {data.errors.products}
            </div>
          ) : products.length === 0 ? (
            <div className="insight-empty">No product sales recorded yet.</div>
          ) : (
            <div className="insight-product-list">
              {products.map((p: Product, i: number) => (
                <div className="insight-product" key={p.product_id}>
                  <div className="insight-product-top">
                    <span className="insight-rank">{i + 1}</span>
                    <div className="insight-product-name">
                      <strong>{p.product_name}</strong>
                      <small>{p.units_sold} units sold</small>
                    </div>
                    <b>{money(p.revenue)}</b>
                  </div>
                  <div className="insight-progress-track">
                    <div className="insight-progress-fill" style={{
                      width: `${p.units_sold / maxProduct * 100}%`
                    }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="insight-panel">
          <div className="insight-panel-heading">
            <div><h2>Confirmed revenue comparison</h2><p>Latest 28 days versus prior 28 days</p></div>
            <TrendingUp size={20} />
          </div>
          {data.errors.workforce ? (
            <div className="insight-empty" role="alert">
              Analysis status could not be loaded: {data.errors.workforce}
            </div>
          ) : sales?.growth_comparison.status === "available" ? (
            <div className="forecast-content">
              <span className="eyebrow">CONFIRMED REVENUE</span>
              <strong>
                {sales.growth_comparison.revenue_change_percent == null
                  ? "Not comparable"
                  : `${sales.growth_comparison.revenue_change_percent > 0 ? "+" : ""}${sales.growth_comparison.revenue_change_percent}%`}
              </strong>
              <p>Latest period: {money(sales.growth_comparison.current_revenue)}</p>
              <p>Previous period: {money(sales.growth_comparison.previous_revenue)}</p>
            </div>
          ) : (
            <div className="insight-empty">
              {latestRun?.status === "completed"
                ? "There are not yet 28 days of confirmed orders to compare."
                : "Run an analysis to compare confirmed revenue periods."}
            </div>
          )}
        </article>
      </section>

      <div className="insight-section-title" id="ai-workforce">
        <div><span className="eyebrow">MERCHANT DECISION SUPPORT</span><h2>AI workforce</h2></div>
        <span className="insight-live-label"><BrainCircuit size={15} /> Analysis only · actions require approval</span>
      </div>

      {analysisError && (
        <div className="insight-inline-error" role="alert">{analysisError}</div>
      )}
      {data.errors.workforce && (
        <div className="insight-empty" role="alert">
          Workforce status could not be loaded: {data.errors.workforce}
        </div>
      )}
      <section className="insight-agent-grid">
        {agents.map((agent) => (
          <article className="insight-panel insight-agent-card" key={agent.agent_type}>
            <div className="insight-panel-heading">
              <div><h2>{agent.name}</h2><p>{agent.agent_type} agent</p></div>
              <span className={`agent-status status-${agent.status}`}>
                {agent.status.replaceAll("_", " ")}
              </span>
            </div>
            <p className="agent-last-run">
              {agent.execution_completed_at
                ? `Completed ${new Date(agent.execution_completed_at).toLocaleString("en-IN")}`
                : agent.status === "running"
                  ? "Analysis is running"
                  : agent.status === "failed"
                    ? agent.error || "This agent did not complete."
                    : "No execution recorded"}
            </p>
            {agent.agent_type === "sales" && sales && (
              <div className="agent-metrics">
                <span>{sales.metrics.confirmed_orders} confirmed orders</span>
                <strong>{money(sales.metrics.confirmed_revenue)}</strong>
                <span>AOV {money(sales.metrics.average_order_value)}</span>
              </div>
            )}
          </article>
        ))}
      </section>

      <section className="insight-lower-grid">
        <article className="insight-panel">
          <div className="insight-panel-heading">
            <div><h2>Inventory analysis</h2><p>Stock against thresholds and recent confirmed sales</p></div>
            <Boxes size={20} />
          </div>
          {!inventory ? (
            <div className="insight-empty">
              {latestRun?.status === "running" ? "Inventory analysis is running..." : "Run an analysis to view inventory findings."}
            </div>
          ) : inventory.products.length === 0 ? (
            <div className="insight-empty">No active products were available for inventory analysis.</div>
          ) : (
            <div className="demand-table-wrap">
              <table className="demand-table">
                <thead><tr>
                  <th>Product</th><th>Stock / threshold</th><th>28-day sales</th>
                  <th>Days of stock</th><th>Suggested reorder</th>
                </tr></thead>
                <tbody>
                  {inventory.products.map((product) => (
                    <tr key={product.product_id}>
                      <td><strong>{product.product_name}</strong></td>
                      <td>{product.current_stock ?? "Unknown"} / {product.low_stock_threshold ?? "Unknown"}</td>
                      <td>{product.units_sold_last_28_days} units</td>
                      <td>{product.estimated_days_of_stock ?? "Insufficient history"}</td>
                      <td>{product.suggested_reorder_quantity ?? "Not estimated"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {inventory?.methodology && <p className="insight-disclaimer">{inventory.methodology}</p>}
        </article>

        <article className="insight-panel">
          <div className="insight-panel-heading">
            <div><h2>Demand trends</h2><p>Experimental historical-average baseline · 7-day horizon</p></div>
            <TrendingUp size={20} />
          </div>
          {demandProducts.length === 0 ? (
            <div className="insight-empty">
              {latestRun?.status === "running" ? "Demand analysis is running..." : "Run an analysis to view demand trends."}
            </div>
          ) : (
            <div className="demand-table-wrap">
              <table className="demand-table">
                <thead><tr>
                  <th>Product</th><th>Recent / prior 7 days</th><th>Trend</th><th>Next 7-day estimate</th>
                </tr></thead>
                <tbody>
                  {demandProducts.map((product) => (
                    <tr key={product.product_id}>
                      <td><strong>{product.product_name}</strong><small>{product.history_window_days} days · {product.confirmed_sale_days} sale days</small></td>
                      <td>{product.units_sold_last_7_days} / {product.units_sold_previous_7_days} units</td>
                      <td>{product.trend.replaceAll("_", " ")}</td>
                      <td>{product.estimated_units_next_7_days ?? product.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {demand?.limitations && <p className="insight-disclaimer">{demand.limitations}</p>}
        </article>
      </section>

      <section className="insight-panel recommendations-panel">
        <div className="insight-panel-heading">
          <div>
            <h2>Prioritized merchant action plan</h2>
            <p>
              {ai
                ? `Analysis completed ${new Date(ai.completed_at).toLocaleString("en-IN")}`
                : "Recommendations appear after a completed analysis"}
            </p>
          </div>
          <Activity size={20} />
        </div>
        {!ai ? (
          <div className="insight-empty">
            {latestRun?.status === "failed"
              ? `The last analysis failed: ${latestRun.error || "Please retry."}`
              : latestRun?.status === "running"
                ? "Analysis is running; results will appear when it completes."
                : "No analysis has run yet."}
          </div>
        ) : recommendations.length === 0 ? (
          <div className="insight-empty">Analysis completed. No recommendations were generated from the available data.</div>
        ) : (
          <div className="recommendation-list">
            {recommendations.map((finding: Finding) => (
              <article className="recommendation-item" key={finding.id}>
                <div className="recommendation-top">
                  <span className="recommendation-category">{finding.category}</span>
                  <span className={`insight-priority priority-${finding.priority}`}>{finding.priority}</span>
                </div>
                <h3>{finding.title}</h3>
                <p>{finding.explanation}</p>
                <div className="recommendation-evidence">
                  <strong>Evidence</strong>
                  {Object.entries(finding.evidence).map(([label, value]) => (
                    <span key={label}>{label.replaceAll("_", " ")}: {displayEvidence(value)}</span>
                  ))}
                </div>
                <div className="recommendation-action"><TrendingUp size={15} />{finding.recommendation}</div>
                <span className="action-approval-status">
                  Analysis completed · Recommendation generated · Merchant action pending approval
                </span>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="insight-panel">
        <div className="insight-panel-heading">
          <div><h2>Execution history</h2><p>Latest persisted workforce runs</p></div>
          <Clock3 size={20} />
        </div>
        {!data.workforce?.history.length ? (
          <div className="insight-empty">No workforce execution history yet.</div>
        ) : (
          <div className="workforce-history">
            {data.workforce.history.map((run) => (
              <div key={run.task_id}>
                <span className={`agent-status status-${run.status}`}>{run.status}</span>
                <span>{run.created_at ? new Date(run.created_at).toLocaleString("en-IN") : "—"}</span>
                <span>{run.report?.action_plan?.total ?? 0} recommendations</span>
                {run.error && <small>{run.error}</small>}
              </div>
            ))}
          </div>
        )}
      </section>

      <footer className="insights-footer">
        <span>Last analysis: {ai?.completed_at ? new Date(ai.completed_at).toLocaleString("en-IN") : "Never"}</span>
        <span>DUKAANTRA · Merchant intelligence</span>
      </footer>
    </main>
  );
}
