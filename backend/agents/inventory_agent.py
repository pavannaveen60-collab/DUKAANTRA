"""Evidence-based inventory and reorder analysis."""

import math
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from models.inventory import Inventory
from models.order import Order
from models.order_item import OrderItem
from models.product import Product
from services.analytics_service import verify_shop_ownership


HISTORY_DAYS = 28
REORDER_LEAD_DAYS = 14
STOCKOUT_WARNING_DAYS = 7


def _safe_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def build_inventory_report(
    products: list[tuple[Any, Any]],
    sales_rows: list[Any],
    today: date | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    start_date = today - timedelta(days=HISTORY_DAYS - 1)
    sales = {}
    for row in sales_rows:
        first_sale = getattr(row, "first_sale", None)
        if isinstance(first_sale, datetime):
            first_sale = first_sale.date()
        if not isinstance(first_sale, date):
            first_sale = None
        sales[row.product_id] = {
            "units": _safe_count(getattr(row, "units_sold", 0)),
            "sale_days": _safe_count(getattr(row, "sale_days", 0)),
            "history_sale_days": _safe_count(getattr(row, "history_sale_days", 0)),
            "first_sale": first_sale,
        }

    findings: list[dict[str, Any]] = []
    analyzed = []

    for product, inventory in products:
        product_id = str(product.id)
        name = str(product.name or "Unnamed product")
        if inventory is None:
            analyzed.append({
                "product_id": product_id,
                "product_name": name,
                "status": "missing_inventory",
                "current_stock": None,
                "low_stock_threshold": None,
                "units_sold_last_28_days": 0,
                "estimated_daily_demand": None,
                "estimated_days_of_stock": None,
                "suggested_reorder_quantity": None,
                "history_status": "insufficient_data",
            })
            findings.append({
                "id": f"inventory:{product_id}:missing-record",
                "agent": "inventory",
                "category": "inventory",
                "priority": "medium",
                "product_id": product_id,
                "product_name": name,
                "title": f"Set an inventory count for {name}",
                "explanation": "No inventory record is available, so stock levels and reorder quantities cannot be verified.",
                "evidence": {"current_stock": None, "low_stock_threshold": None},
                "recommendation": "Count this product and initialize its inventory before making a replenishment decision.",
                "action_status": "pending_approval",
            })
            continue

        try:
            stock = max(0, int(inventory.quantity))
            threshold = max(0, int(inventory.low_stock_threshold))
        except (TypeError, ValueError, OverflowError):
            analyzed.append({
                "product_id": product_id,
                "product_name": name,
                "status": "invalid_inventory",
                "current_stock": None,
                "low_stock_threshold": None,
                "units_sold_last_28_days": 0,
                "estimated_daily_demand": None,
                "estimated_days_of_stock": None,
                "suggested_reorder_quantity": None,
                "history_status": "insufficient_data",
            })
            continue

        product_sales = sales.get(product.id)
        units_sold = product_sales["units"] if product_sales else 0
        first_sale = product_sales["first_sale"] if product_sales else None
        span_days = (
            (today - max(start_date, first_sale)).days + 1
            if first_sale is not None else 0
        )
        observed_days = min(HISTORY_DAYS, max(1, span_days))
        sufficient_history = bool(
            product_sales
            and span_days >= 14
            and product_sales["sale_days"] >= 3
        )
        mature_product_history = bool(
            product_sales
            and product_sales["first_sale"] is not None
            and product_sales["history_sale_days"] >= 3
            and (today - product_sales["first_sale"]).days >= 14
        )
        daily_demand = units_sold / observed_days if sufficient_history else None
        days_of_stock = stock / daily_demand if daily_demand and daily_demand > 0 else None
        reorder_quantity = (
            max(
                0,
                math.ceil(daily_demand * REORDER_LEAD_DAYS + threshold - stock),
            )
            if daily_demand is not None
            else None
        )

        analyzed.append({
            "product_id": product_id,
            "product_name": name,
            "status": "analyzed",
            "current_stock": stock,
            "low_stock_threshold": threshold,
            "units_sold_last_28_days": units_sold,
            "estimated_daily_demand": round(daily_demand, 2) if daily_demand is not None else None,
            "estimated_days_of_stock": round(days_of_stock, 1) if days_of_stock is not None else None,
            "suggested_reorder_quantity": reorder_quantity,
            "history_status": "sufficient" if sufficient_history else "insufficient_data",
        })

        evidence = {
            "current_stock": stock,
            "low_stock_threshold": threshold,
            "units_sold_last_28_days": units_sold,
            "history_days": min(HISTORY_DAYS, span_days),
            "confirmed_sale_days": product_sales["sale_days"] if product_sales else 0,
        }
        if stock <= threshold:
            priority = "critical" if stock == 0 else "high"
            recommendation = (
                f"Plan to reorder approximately {reorder_quantity} units to cover "
                f"a {REORDER_LEAD_DAYS}-day lead time plus the stock threshold."
                if reorder_quantity is not None
                else "Review supplier availability and verify demand before setting a reorder quantity."
            )
            findings.append({
                "id": f"inventory:{product_id}:below-threshold",
                "agent": "inventory",
                "category": "inventory",
                "priority": priority,
                "product_id": product_id,
                "product_name": name,
                "title": f"{'Out of stock' if stock == 0 else 'Below stock threshold'}: {name}",
                "explanation": (
                    f"Available stock ({stock}) is at or below its configured threshold ({threshold})."
                ),
                "evidence": {
                    **evidence,
                    "estimated_daily_demand": round(daily_demand, 2) if daily_demand is not None else None,
                    "estimated_days_of_stock": round(days_of_stock, 1) if days_of_stock is not None else None,
                    "suggested_reorder_quantity": reorder_quantity,
                    "reorder_lead_days_assumption": REORDER_LEAD_DAYS,
                },
                "recommendation": recommendation,
                "action_status": "pending_approval",
            })
        elif days_of_stock is not None and days_of_stock <= STOCKOUT_WARNING_DAYS:
            findings.append({
                "id": f"inventory:{product_id}:stockout-risk",
                "agent": "inventory",
                "category": "inventory",
                "priority": "high" if days_of_stock <= 3 else "medium",
                "product_id": product_id,
                "product_name": name,
                "title": f"Stock may run low: {name}",
                "explanation": (
                    f"At the recent estimated demand of {daily_demand:.2f} units/day, "
                    f"current stock covers about {days_of_stock:.1f} days."
                ),
                "evidence": {
                    **evidence,
                    "estimated_daily_demand": round(daily_demand, 2),
                    "estimated_days_of_stock": round(days_of_stock, 1),
                    "stockout_warning_days": STOCKOUT_WARNING_DAYS,
                    "suggested_reorder_quantity": reorder_quantity,
                },
                "recommendation": "Review replenishment timing; this is a historical average, not a guaranteed forecast.",
                "action_status": "pending_approval",
            })

        if mature_product_history and stock > 0 and units_sold == 0:
            findings.append({
                "id": f"inventory:{product_id}:no-recent-sales",
                "agent": "inventory",
                "category": "inventory",
                "priority": "low",
                "product_id": product_id,
                "product_name": name,
                "title": f"Review slow-moving stock: {name}",
                "explanation": "The product has stock but no confirmed sales in the 28-day observation window.",
                "evidence": {**evidence, "observation_window_days": HISTORY_DAYS},
                "recommendation": "Review whether this stock should be promoted, transferred, or retained.",
                "action_status": "pending_approval",
            })
        elif sufficient_history and units_sold > 0 and stock >= units_sold * 3:
            findings.append({
                "id": f"inventory:{product_id}:possible-overstock",
                "agent": "inventory",
                "category": "inventory",
                "priority": "low",
                "product_id": product_id,
                "product_name": name,
                "title": f"Review stock coverage: {name}",
                "explanation": "On-hand units are at least three times the units sold during the last 28 days.",
                "evidence": {
                    **evidence,
                    "on_hand_to_28_day_sales_ratio": round(stock / units_sold, 1),
                    "review_rule_ratio": 3,
                },
                "recommendation": "Review replenishment plans and consider a promotion; no stock changes are made automatically.",
                "action_status": "pending_approval",
            })

    return {
        "agent": "Inventory Intelligence",
        "status": "completed",
        "products_analyzed": len(analyzed),
        "products": analyzed,
        "findings": findings,
        "methodology": (
            "Confirmed order-item sales over up to 28 calendar days. Demand-based "
            "reorder quantities require at least 14 days since first observed sale "
            "and at least 3 distinct confirmed-sale days. A 14-day supplier lead "
            "time is an explicit planning assumption, not a known supplier term."
        ),
    }


def run_inventory_agent(
    db: Session,
    current_user: Any,
    shop_id: UUID,
) -> dict[str, Any]:
    verify_shop_ownership(db, current_user, shop_id)
    product_rows = db.execute(
        select(Product, Inventory)
        .outerjoin(
            Inventory,
            and_(
                Inventory.product_id == Product.id,
                Inventory.shop_id == shop_id,
            ),
        )
        .where(
            Product.shop_id == shop_id,
            Product.is_active.is_(True),
        )
        .order_by(Product.name)
    ).all()
    product_ids = [product.id for product, _inventory in product_rows]
    sales_rows = []
    if product_ids:
        cutoff = datetime.combine(
            date.today() - timedelta(days=HISTORY_DAYS - 1),
            time.min,
            tzinfo=timezone.utc,
        )
        sales_rows = db.execute(
            select(
                OrderItem.product_id.label("product_id"),
                func.coalesce(
                    func.sum(
                        case(
                            (Order.created_at >= cutoff, OrderItem.quantity),
                            else_=0,
                        )
                    ),
                    0,
                ).label("units_sold"),
                func.count(
                    func.distinct(
                        func.date(
                            case(
                                (Order.created_at >= cutoff, Order.created_at),
                                else_=None,
                            )
                        )
                    )
                ).label("sale_days"),
                func.count(func.distinct(func.date(Order.created_at))).label("history_sale_days"),
                func.min(Order.created_at).label("first_sale"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                Order.shop_id == shop_id,
                Order.status == "confirmed",
                OrderItem.product_id.in_(product_ids),
            )
            .group_by(OrderItem.product_id)
        ).all()
    return build_inventory_report(product_rows, sales_rows)
