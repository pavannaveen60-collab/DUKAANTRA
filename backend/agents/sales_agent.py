"""Confirmed-order sales performance and growth opportunities."""

import math
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session, aliased

from agents.growth_agent import build_growth_findings
from models.inventory import Inventory
from models.order import Order
from models.order_item import OrderItem
from models.product import Product
from services.analytics_service import verify_shop_ownership


SALES_WINDOW_DAYS = 28


def _as_money(value: Any) -> float:
    try:
        amount = float(Decimal(str(value or 0)))
        return round(amount, 2) if math.isfinite(amount) else 0.0
    except (ValueError, TypeError, ArithmeticError):
        return 0.0


def _as_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (ValueError, TypeError, OverflowError):
        return 0


def _stock(inventory: Any) -> int | None:
    if inventory is None:
        return None
    try:
        return max(0, int(inventory.quantity))
    except (ValueError, TypeError, OverflowError):
        return None


def build_sales_report(
    order_summary: Any,
    product_sales: list[Any],
    products: list[tuple[Any, Any]],
    co_purchase_rows: list[Any],
    period_comparison: Any,
) -> dict[str, Any]:
    confirmed_orders = _as_count(order_summary.order_count)
    confirmed_revenue = _as_money(order_summary.revenue)
    average_order_value = (
        round(confirmed_revenue / confirmed_orders, 2)
        if confirmed_orders
        else 0.0
    )
    product_by_id = {product.id: (product, inventory) for product, inventory in products}
    sales_by_id = {
        row.product_id: {
            "units_sold": _as_count(row.units_sold),
            "revenue": _as_money(row.revenue),
        }
        for row in product_sales
    }

    ranked = sorted(
        (
            {
                "product_id": str(product_id),
                "product_name": str(product_by_id[product_id][0].name or "Unnamed product"),
                "units_sold": values["units_sold"],
                "revenue": values["revenue"],
                "current_stock": _stock(product_by_id[product_id][1]),
            }
            for product_id, values in sales_by_id.items()
            if product_id in product_by_id
        ),
        key=lambda item: (-item["units_sold"], -item["revenue"], item["product_name"].casefold()),
    )
    slow_movers = []
    for product, inventory in products:
        values = sales_by_id.get(product.id, {"units_sold": 0, "revenue": 0.0})
        if values["units_sold"] == 0:
            slow_movers.append({
                "product_id": str(product.id),
                "product_name": str(product.name or "Unnamed product"),
                "units_sold": 0,
                "revenue": 0.0,
                "current_stock": _stock(inventory),
            })

    findings: list[dict[str, Any]] = []
    growth = build_growth_findings(period_comparison)
    if growth["finding"] is not None:
        findings.append(growth["finding"])
    if confirmed_orders:
        findings.append({
            "id": "sales:confirmed-performance",
            "agent": "sales",
            "category": "sales",
            "priority": "low",
            "title": "Confirmed sales performance",
            "explanation": f"{confirmed_orders} confirmed orders generated ₹{confirmed_revenue:.2f} in recorded revenue.",
            "evidence": {
                "confirmed_orders": confirmed_orders,
                "confirmed_revenue": confirmed_revenue,
                "average_order_value": average_order_value,
                "units_sold_in_window": sum(item["units_sold"] for item in ranked),
                "window_days": SALES_WINDOW_DAYS,
            },
            "recommendation": "Compare this period with the next 28-day period to evaluate growth.",
            "action_status": "pending_approval",
        })

    if len(ranked) >= 2:
        leading = ranked[:2]
        findings.append({
            "id": f"sales:promotion:{leading[0]['product_id']}:{leading[1]['product_id']}",
            "agent": "sales",
            "category": "growth",
            "priority": "low",
            "title": "Consider promoting top-selling products",
            "explanation": (
                f"{leading[0]['product_name']} ({leading[0]['units_sold']} units) and "
                f"{leading[1]['product_name']} ({leading[1]['units_sold']} units) "
                f"led confirmed unit sales in the last {SALES_WINDOW_DAYS} days."
            ),
            "evidence": {"top_products": leading, "window_days": SALES_WINDOW_DAYS},
            "recommendation": "Consider featuring these products; no price or promotion changes are made.",
            "action_status": "pending_approval",
        })

    for pair in co_purchase_rows:
        order_count = _as_count(pair.order_count)
        first = product_by_id.get(pair.product_a_id)
        second = product_by_id.get(pair.product_b_id)
        if order_count < 2 or first is None or second is None:
            continue
        findings.append({
            "id": f"sales:bundle:{pair.product_a_id}:{pair.product_b_id}",
            "agent": "sales",
            "category": "growth",
            "priority": "medium",
            "title": f"Explore a bundle: {first[0].name} and {second[0].name}",
            "explanation": f"Both products appeared in {order_count} distinct confirmed orders in the observation window.",
            "evidence": {
                "product_ids": [str(pair.product_a_id), str(pair.product_b_id)],
                "product_names": [str(first[0].name), str(second[0].name)],
                "co_purchase_orders": order_count,
                "window_days": SALES_WINDOW_DAYS,
            },
            "recommendation": "Evaluate a bundle for these products; this report does not change prices or create offers.",
            "action_status": "pending_approval",
        })

    for item in slow_movers:
        if item["current_stock"] is None or item["current_stock"] <= 0:
            continue
        findings.append({
            "id": f"sales:slow-moving:{item['product_id']}",
            "agent": "sales",
            "category": "growth",
            "priority": "low",
            "product_id": item["product_id"],
            "product_name": item["product_name"],
            "title": f"Review unsold stock: {item['product_name']}",
            "explanation": (
                f"{item['current_stock']} units are on hand and no units were sold "
                f"in the last {SALES_WINDOW_DAYS} days."
            ),
            "evidence": {**item, "window_days": SALES_WINDOW_DAYS},
            "recommendation": "Review product visibility, category fit, or a merchant-approved promotion.",
            "action_status": "pending_approval",
        })

    return {
        "agent": "Sales and Growth Intelligence",
        "status": "completed",
        "metrics": {
            "confirmed_orders": confirmed_orders,
            "confirmed_revenue": confirmed_revenue,
            "average_order_value": average_order_value,
            "units_sold": sum(item["units_sold"] for item in ranked),
            "window_days": SALES_WINDOW_DAYS,
        },
        "growth_comparison": growth,
        "best_sellers": ranked[:5],
        "slow_movers": slow_movers,
        "findings": findings,
        "methodology": "Revenue, order count, and product sales use only orders whose status is confirmed. Product performance covers the last 28 calendar days.",
    }


def run_sales_agent(
    db: Session,
    current_user: Any,
    shop_id: UUID,
) -> dict[str, Any]:
    verify_shop_ownership(db, current_user, shop_id)
    cutoff = datetime.combine(
        date.today() - timedelta(days=SALES_WINDOW_DAYS - 1),
        time.min,
        tzinfo=timezone.utc,
    )
    previous_cutoff = cutoff - timedelta(days=SALES_WINDOW_DAYS)
    order_summary = db.execute(
        select(
            func.count(Order.id).label("order_count"),
            func.coalesce(func.sum(Order.total_amount), 0).label("revenue"),
        ).where(
            Order.shop_id == shop_id,
            Order.status == "confirmed",
            Order.created_at >= cutoff,
        )
    ).one()
    period_comparison = db.execute(
        select(
            func.count(
                func.distinct(
                    case(
                        (Order.created_at >= cutoff, Order.id),
                        else_=None,
                    )
                )
            ).label("current_orders"),
            func.coalesce(
                func.sum(
                    case(
                        (Order.created_at >= cutoff, Order.total_amount),
                        else_=0,
                    )
                ),
                0,
            ).label("current_revenue"),
            func.count(
                func.distinct(
                    case(
                        (
                            and_(
                                Order.created_at >= previous_cutoff,
                                Order.created_at < cutoff,
                            ),
                            Order.id,
                        ),
                        else_=None,
                    )
                )
            ).label("previous_orders"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                Order.created_at >= previous_cutoff,
                                Order.created_at < cutoff,
                            ),
                            Order.total_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("previous_revenue"),
        )
        .where(
            Order.shop_id == shop_id,
            Order.status == "confirmed",
            Order.created_at >= previous_cutoff,
        )
    ).one()
    product_sales = db.execute(
        select(
            OrderItem.product_id.label("product_id"),
            func.coalesce(func.sum(OrderItem.quantity), 0).label("units_sold"),
            func.coalesce(func.sum(OrderItem.subtotal), 0).label("revenue"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.shop_id == shop_id,
            Order.status == "confirmed",
            Order.created_at >= cutoff,
        )
        .group_by(OrderItem.product_id)
    ).all()
    products = db.execute(
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

    left = aliased(OrderItem)
    right = aliased(OrderItem)
    co_purchase_rows = db.execute(
        select(
            left.product_id.label("product_a_id"),
            right.product_id.label("product_b_id"),
            func.count(func.distinct(Order.id)).label("order_count"),
        )
        .join(Order, Order.id == left.order_id)
        .join(
            right,
            and_(
                right.order_id == left.order_id,
                left.product_id < right.product_id,
            ),
        )
        .where(
            Order.shop_id == shop_id,
            Order.status == "confirmed",
            Order.created_at >= cutoff,
        )
        .group_by(left.product_id, right.product_id)
        .order_by(func.count(func.distinct(Order.id)).desc())
        .limit(5)
    ).all()
    return build_sales_report(
        order_summary,
        product_sales,
        products,
        co_purchase_rows,
        period_comparison,
    )
