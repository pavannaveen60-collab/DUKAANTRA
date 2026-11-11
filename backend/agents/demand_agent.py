"""Historical-sales demand trend analysis with conservative baselines."""

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.order import Order
from models.order_item import OrderItem
from models.product import Product
from services.analytics_service import verify_shop_ownership


HISTORY_DAYS = 28
FORECAST_DAYS = 7
MIN_HISTORY_DAYS = 14
MIN_SALE_DAYS = 3


def build_demand_report(
    products: list[Any],
    daily_rows: list[Any],
    today: date | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    start = today - timedelta(days=HISTORY_DAYS - 1)
    daily: dict[Any, dict[date, int]] = {}
    for row in daily_rows:
        sale_date = row.sale_date.date() if isinstance(row.sale_date, datetime) else row.sale_date
        if not isinstance(sale_date, date):
            continue
        try:
            units = max(0, int(row.units_sold or 0))
        except (TypeError, ValueError, OverflowError):
            continue
        product_sales = daily.setdefault(row.product_id, {})
        product_sales[sale_date] = product_sales.get(sale_date, 0) + units

    analyses: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    for product in products:
        product_id = str(product.id)
        name = str(product.name or "Unnamed product")
        sales = daily.get(product.id, {})
        valid_sales = {
            day: units for day, units in sales.items()
            if start <= day <= today
        }
        first_sale = min(valid_sales) if valid_sales else None
        observation_days = (
            min(HISTORY_DAYS, max(1, (today - max(start, first_sale)).days + 1))
            if first_sale is not None
            else 0
        )
        total_units = sum(valid_sales.values())
        sale_days = sum(units > 0 for units in valid_sales.values())
        sufficient = observation_days >= MIN_HISTORY_DAYS and sale_days >= MIN_SALE_DAYS

        recent_units = sum(
            units for day, units in valid_sales.items()
            if day > today - timedelta(days=7)
        )
        previous_units = sum(
            units for day, units in valid_sales.items()
            if today - timedelta(days=14) < day <= today - timedelta(days=7)
        )
        trend = "insufficient_data"
        if sufficient:
            if previous_units == 0:
                trend = "emerging" if recent_units > 0 else "no_recent_demand"
            elif recent_units >= previous_units * 1.5:
                trend = "increasing"
            elif recent_units <= previous_units * 0.5:
                trend = "decreasing"
            else:
                trend = "stable"

        forecast = (
            round(total_units / observation_days * FORECAST_DAYS, 1)
            if sufficient
            else None
        )
        analysis = {
            "product_id": product_id,
            "product_name": name,
            "status": "forecast_available" if sufficient else "insufficient_data",
            "history_window_days": observation_days,
            "confirmed_sale_days": sale_days,
            "units_sold_in_observation_window": total_units,
            "units_sold_last_7_days": recent_units,
            "units_sold_previous_7_days": previous_units,
            "trend": trend,
            "forecast_period_days": FORECAST_DAYS,
            "estimated_units_next_7_days": forecast,
            "methodology": (
                "Historical average: observed confirmed units divided by observed calendar days, "
                "then multiplied by 7."
            ) if sufficient else None,
            "limitations": (
                "Experimental baseline only; assumes recent average demand continues and does not model seasonality, promotions, stockouts, or future events."
            ) if sufficient else (
                f"Requires at least {MIN_HISTORY_DAYS} days of observed history and "
                f"{MIN_SALE_DAYS} distinct confirmed-sale days."
            ),
        }
        analyses.append(analysis)

        if sufficient and trend in ("increasing", "decreasing"):
            delta = (
                round((recent_units - previous_units) / previous_units * 100, 1)
                if previous_units
                else None
            )
            findings.append({
                "id": f"demand:{product_id}:{trend}",
                "agent": "demand",
                "category": "demand",
                "priority": "medium" if trend == "increasing" else "low",
                "product_id": product_id,
                "product_name": name,
                "title": f"{'Rising' if trend == 'increasing' else 'Falling'} demand: {name}",
                "explanation": (
                    f"Confirmed units changed from {previous_units} in the prior 7 days "
                    f"to {recent_units} in the latest 7 days ({delta:+.1f}%)."
                ),
                "evidence": {
                    "units_sold_last_7_days": recent_units,
                    "units_sold_previous_7_days": previous_units,
                    "change_percent": delta,
                    "history_window_days": observation_days,
                },
                "recommendation": (
                    "Review replenishment plans and verify the trend against upcoming orders."
                    if trend == "increasing"
                    else "Review availability, seasonality, and product visibility before changing plans."
                ),
                "action_status": "pending_approval",
            })

    return {
        "agent": "Demand Intelligence",
        "status": "completed",
        "forecast_status": (
            "available" if any(item["status"] == "forecast_available" for item in analyses)
            else "insufficient_data"
        ),
        "forecast_period_days": FORECAST_DAYS,
        "products_analyzed": len(analyses),
        "products": analyses,
        "findings": findings,
        "methodology": (
            "Experimental 7-day baseline derived only from confirmed product sales. "
            "A forecast is withheld unless at least 14 calendar days and 3 distinct "
            "confirmed-sale days are observed. Demand is marked increasing when the "
            "latest 7-day units are at least 1.5 times the previous 7 days, and "
            "decreasing at or below 0.5 times."
        ),
        "limitations": (
            "This is a simple historical-average estimate, not a trained or validated forecasting model."
        ),
    }


def run_demand_agent(
    db: Session,
    current_user: Any,
    shop_id: UUID,
) -> dict[str, Any]:
    verify_shop_ownership(db, current_user, shop_id)
    products = db.scalars(
        select(Product)
        .where(
            Product.shop_id == shop_id,
            Product.is_active.is_(True),
        )
        .order_by(Product.name)
    ).all()
    rows = []
    if products:
        cutoff = datetime.combine(
            date.today() - timedelta(days=HISTORY_DAYS - 1),
            time.min,
            tzinfo=timezone.utc,
        )
        rows = db.execute(
            select(
                OrderItem.product_id.label("product_id"),
                func.date(Order.created_at).label("sale_date"),
                func.coalesce(func.sum(OrderItem.quantity), 0).label("units_sold"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .join(Product, Product.id == OrderItem.product_id)
            .where(
                Order.shop_id == shop_id,
                Order.status == "confirmed",
                Order.created_at >= cutoff,
                Product.shop_id == shop_id,
                Product.is_active.is_(True),
            )
            .group_by(OrderItem.product_id, func.date(Order.created_at))
        ).all()
    return build_demand_report(products, rows)
