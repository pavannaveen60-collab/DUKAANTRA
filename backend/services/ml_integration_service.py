from datetime import date, datetime, time, timedelta
from decimal import Decimal
from statistics import median
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.inventory import Inventory
from models.order import Order
from models.order_item import OrderItem
from models.product import Product
from models.shop import Shop

MIN_HISTORY_DAYS = 14
HISTORY_WINDOW_DAYS = 28


def verify_shop(db: Session, current_user, shop_id: UUID):
    shop = db.scalar(
        select(Shop).where(
            Shop.id == shop_id,
            Shop.owner_id == current_user.id,
        )
    )
    if shop is None:
        raise ValueError("Shop not found or access denied.")
    return shop


def get_product_daily_history(
    db: Session,
    shop_id: UUID,
    product_id: UUID,
    start_date: datetime,
    end_date: date | None = None,
):
    conditions = [
        Order.shop_id == shop_id,
        Order.status == "confirmed",
        OrderItem.product_id == product_id,
        Order.created_at >= start_date,
    ]
    if end_date is not None:
        conditions.append(
            Order.created_at < datetime.combine(end_date, time.min)
        )
    results = db.execute(
        select(
            func.date(Order.created_at).label("sale_date"),
            func.coalesce(func.sum(OrderItem.quantity), 0).label("units_sold"),
        )
        .join(OrderItem, OrderItem.order_id == Order.id)
        .where(*conditions)
        .group_by(func.date(Order.created_at))
        .order_by(func.date(Order.created_at))
    ).all()
    return {row.sale_date: int(row.units_sold) for row in results}


def get_demand_and_stockout_predictions(
    db: Session,
    current_user,
    shop_id: UUID,
):
    verify_shop(db, current_user, shop_id)
    products = db.execute(
        select(Product, Inventory)
        .join(Inventory, Inventory.product_id == Product.id)
        .where(
            Product.shop_id == shop_id,
            Product.is_active.is_(True),
            Inventory.shop_id == shop_id,
        )
    ).all()
    today = date.today()
    history_start = today - timedelta(days=HISTORY_WINDOW_DAYS)
    predictions = []

    for product, inventory in products:
        history = get_product_daily_history(
            db,
            shop_id,
            product.id,
            datetime.combine(history_start, time.min),
            today,
        )
        observed_history = {
            sale_date: units
            for sale_date, units in history.items()
            if history_start <= sale_date < today
        }
        latest_week = [
            units
            for sale_date, units in observed_history.items()
            if today - timedelta(days=7) <= sale_date < today
        ]
        confirmed_sales_observations = len(observed_history)
        enough_history = confirmed_sales_observations >= MIN_HISTORY_DAYS

        if enough_history:
            mean_units_per_observed_sale_day = (
                sum(observed_history.values()) / confirmed_sales_observations
            )
            estimated_7_day_demand = round(
                mean_units_per_observed_sale_day * 7, 2
            )
            predicted_daily_demand = round(estimated_7_day_demand / 7, 2)
            current_stock = max(0, int(inventory.quantity))
            likely_stockout = estimated_7_day_demand > current_stock
            stockout = {
                "status": "deterministic_baseline",
                "risk_level": "elevated" if likely_stockout else "not_indicated",
                "stockout_probability": None,
                "method": (
                    "compare current stock with mean confirmed units per "
                    "observed sale day over the prior 28 days, scaled to 7 days"
                ),
                "forecast_horizon_days": 7,
            }
            status = "experimental_baseline"
        else:
            estimated_7_day_demand = None
            predicted_daily_demand = None
            current_stock = max(0, int(inventory.quantity))
            stockout = {
                "status": "insufficient_data",
                "risk_level": None,
                "stockout_probability": None,
                "forecast_horizon_days": 7,
            }
            status = "insufficient_data"

        predictions.append({
            "product_id": str(product.id),
            "product_name": product.name,
            "current_stock": current_stock,
            "low_stock_threshold": int(inventory.low_stock_threshold),
            "historical_units_last_7_days": sum(latest_week),
            "predicted_daily_demand": predicted_daily_demand,
            "estimated_7_day_demand": estimated_7_day_demand,
            "stockout_risk": stockout,
            "status": status,
            "model_version": None,
            "data_source": "confirmed PostgreSQL merchant sales and current inventory",
            "history_days_with_sales": confirmed_sales_observations,
            "history_days_available": confirmed_sales_observations,
            "confirmed_sales_observations": confirmed_sales_observations,
            "required_confirmed_sales_observations": MIN_HISTORY_DAYS,
            "forecast_method": (
                "mean confirmed units per observed sale day in the prior 28 days, "
                "scaled to 7 days; no missing dates are treated as zero"
            ),
        })

    return {
        "agent": "Demand and Stockout Baseline Intelligence",
        "shop_id": str(shop_id),
        "generated_at": datetime.now().isoformat(),
        "products_analyzed": len(predictions),
        "predictions": predictions,
        "limitations": (
            f"Experimental baseline only. Requires at least {MIN_HISTORY_DAYS} "
            "distinct confirmed-sale dates in the prior 28 days. It does not "
            "treat dates without a recorded sale as zero demand and does not "
            "account for unrecorded demand, stockouts, promotions, or planned "
            "price changes. Stockout status is a comparison, not a probability."
        ),
    }


def _daily_sales_rows(
    db: Session,
    shop_id: UUID,
    start_date: date,
    end_date: date | None = None,
):
    conditions = [
        Order.shop_id == shop_id,
        Order.status == "confirmed",
        Order.created_at >= datetime.combine(start_date, time.min),
    ]
    if end_date is not None:
        conditions.append(
            Order.created_at < datetime.combine(end_date, time.min)
        )
    return db.execute(
        select(
            func.date(Order.created_at).label("sale_date"),
            func.coalesce(func.sum(OrderItem.quantity), 0).label("units"),
            func.coalesce(func.sum(OrderItem.subtotal), 0).label("revenue"),
            func.count(func.distinct(Order.id)).label("orders"),
        )
        .join(OrderItem, OrderItem.order_id == Order.id)
        .where(*conditions)
        .group_by(func.date(Order.created_at))
        .order_by(func.date(Order.created_at))
    ).all()


def get_sales_forecast(db: Session, current_user, shop_id: UUID):
    verify_shop(db, current_user, shop_id)
    today = date.today()
    forecast_date = today + timedelta(days=1)
    history_start = today - timedelta(days=HISTORY_WINDOW_DAYS)
    results = _daily_sales_rows(db, shop_id, history_start, today)
    sales_by_date = {
        row.sale_date: {
            "units": int(row.units),
            "revenue": Decimal(str(row.revenue)),
            "orders": int(row.orders),
        }
        for row in results
    }
    confirmed_sales_observations = len(sales_by_date)
    enough_history = confirmed_sales_observations >= MIN_HISTORY_DAYS
    if not enough_history:
        return {
            "agent": "Sales Forecast Baseline",
            "status": "insufficient_data",
            "message": (
                f"At least {MIN_HISTORY_DAYS} distinct confirmed-sale dates "
                "in the prior 28 days are required."
            ),
            "forecast": None,
            "history_days_available": confirmed_sales_observations,
            "confirmed_sales_observations": confirmed_sales_observations,
            "required_confirmed_sales_observations": MIN_HISTORY_DAYS,
        }

    total_units = sum(row["units"] for row in sales_by_date.values())
    total_revenue = sum(
        (row["revenue"] for row in sales_by_date.values()), Decimal("0.00")
    )
    total_orders = sum(row["orders"] for row in sales_by_date.values())
    return {
        "agent": "Sales Forecast Baseline",
        "status": "experimental_baseline",
        "forecast_date": forecast_date.isoformat(),
        "predicted_revenue": round(
            sum(float(row["revenue"]) for row in sales_by_date.values())
            / confirmed_sales_observations,
            2,
        ),
        "model_version": None,
        "forecast_method": (
            "mean confirmed revenue per observed sale day in the prior 28 days; "
            "no missing dates are treated as zero"
        ),
        "confirmed_sales_observations": confirmed_sales_observations,
        "required_confirmed_sales_observations": MIN_HISTORY_DAYS,
        "historical_data": {
            "days_with_confirmed_sales": confirmed_sales_observations,
            "history_days_available": confirmed_sales_observations,
            "confirmed_sales_observations": confirmed_sales_observations,
            "required_confirmed_sales_observations": MIN_HISTORY_DAYS,
            "total_units": total_units,
            "total_revenue": float(total_revenue),
            "total_orders": total_orders,
        },
        "data_source": "confirmed PostgreSQL merchant transactions",
        "limitations": (
            f"Transparent trailing-average baseline, not a validated ML forecast. "
            f"Requires at least {MIN_HISTORY_DAYS} distinct confirmed-sale dates "
            "in the prior 28 days. Uses only observed confirmed-sale dates; "
            "no-sale dates are not imputed as zero."
        ),
    }


def get_sales_anomaly_report(db: Session, current_user, shop_id: UUID):
    verify_shop(db, current_user, shop_id)
    today = date.today()
    yesterday = today - timedelta(days=1)
    history_start = yesterday - timedelta(days=HISTORY_WINDOW_DAYS)
    results = _daily_sales_rows(db, shop_id, history_start, today)
    sales_by_date = {
        row.sale_date: {
            "units": int(row.units),
            "revenue": Decimal(str(row.revenue)),
            "orders": int(row.orders),
        }
        for row in results
    }
    yesterday_data = sales_by_date.get(
        yesterday,
        {"units": 0, "revenue": Decimal("0.00"), "orders": 0},
    )
    baseline_observations = {
        sale_date: values
        for sale_date, values in sales_by_date.items()
        if history_start <= sale_date < yesterday
    }
    baseline_values = [
        float(values["revenue"])
        for values in baseline_observations.values()
    ]
    if (
        len(baseline_observations) < MIN_HISTORY_DAYS
        or yesterday not in sales_by_date
    ):
        return {
            "agent": "Sales Anomaly Baseline",
            "status": "insufficient_data",
            "message": (
                f"At least {MIN_HISTORY_DAYS} distinct confirmed-sale dates "
                "before yesterday and a confirmed-sale observation for yesterday "
                "are required."
            ),
            "anomaly": None,
            "confirmed_sales_observations": len(baseline_observations),
            "required_confirmed_sales_observations": MIN_HISTORY_DAYS,
        }

    median_revenue = median(baseline_values)
    median_absolute_deviation = median(
        [abs(value - median_revenue) for value in baseline_values]
    )
    observed_revenue = float(yesterday_data["revenue"])
    if median_absolute_deviation:
        robust_score = 0.6745 * (observed_revenue - median_revenue) / median_absolute_deviation
        is_anomaly = abs(robust_score) >= 3.5
    else:
        robust_score = None
        is_anomaly = observed_revenue != median_revenue
    units = yesterday_data["units"]
    revenue = yesterday_data["revenue"]
    return {
        "agent": "Sales Anomaly Baseline",
        "status": "experimental_baseline",
        "analysis_date": yesterday.isoformat(),
        "daily_sales": {
            "units_sold": units,
            "revenue": float(revenue),
            "order_count": yesterday_data["orders"],
            "average_price": round(float(revenue / units), 2) if units else 0.0,
        },
        "anomaly_detection": {
            "is_anomaly": is_anomaly,
            "robust_deviation_score": round(robust_score, 4)
            if robust_score is not None
            else None,
            "baseline_median_daily_revenue": round(median_revenue, 2),
            "baseline_median_absolute_deviation": round(
                median_absolute_deviation, 2
            ),
            "method": "28-day rolling median absolute deviation; threshold 3.5",
        },
        "data_source": "confirmed PostgreSQL merchant transactions",
        "limitations": (
            "Experimental retrospective heuristic, not a fraud classifier. "
            "Zero-sales days are included; sparse history can make the baseline unstable."
        ),
    }
