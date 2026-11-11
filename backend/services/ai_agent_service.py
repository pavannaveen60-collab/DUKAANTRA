
"""Legacy rule-based helpers; the live API uses the AI Workforce service."""

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.inventory import Inventory
from models.order import Order
from models.order_item import OrderItem
from models.product import Product
from models.shop import Shop

from services.analytics_service import (
    get_sales_overview,
    get_top_selling_products,
)


def verify_shop(db: Session, current_user, shop_id):
    shop = db.scalar(
        select(Shop).where(
            Shop.id == shop_id,
            Shop.owner_id == current_user.id,
        )
    )

    if shop is None:
        raise ValueError("Shop not found or access denied.")

    return shop


# 1. INVENTORY INTELLIGENCE MODULE
def run_inventory_agent(db: Session, current_user, shop_id):
    verify_shop(db, current_user, shop_id)

    records = db.execute(
        select(Inventory, Product)
        .join(Product, Product.id == Inventory.product_id)
        .where(
            Inventory.shop_id == shop_id,
            Product.is_active.is_(True),
        )
    ).all()

    alerts = []

    for inventory, product in records:
        if inventory.quantity <= inventory.low_stock_threshold:
            alerts.append({
                "product_id": str(product.id),
                "product_name": product.name,
                "current_stock": inventory.quantity,
                "low_stock_threshold": inventory.low_stock_threshold,
                "severity": (
                    "critical" if inventory.quantity == 0 else "warning"
                ),
                "recommendation": (
                    f"Restock {product.name}. "
                    f"Current stock is {inventory.quantity} units."
                ),
            })

    return {
        "agent": "Inventory Intelligence Module",
        "total_alerts": len(alerts),
        "alerts": alerts,
    }


# 2. DEMAND FORECASTING MODULE
def run_demand_forecasting_agent(
    db: Session,
    current_user,
    shop_id,
):
    verify_shop(db, current_user, shop_id)

    seven_days_ago = datetime.now() - timedelta(days=7)

    results = db.execute(
        select(
            Product.id,
            Product.name,
            func.coalesce(func.sum(OrderItem.quantity), 0).label(
                "units_sold"
            ),
        )
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Product.shop_id == shop_id,
            Order.shop_id == shop_id,
            Order.status == "confirmed",
            Order.created_at >= seven_days_ago,
        )
        .group_by(Product.id, Product.name)
    ).all()

    forecasts = []

    for row in results:
        average_daily_demand = Decimal(str(row.units_sold)) / Decimal("7")
        predicted_demand = int(
            average_daily_demand * Decimal("7")
        )

        forecasts.append({
            "product_id": str(row.id),
            "product_name": row.name,
            "units_sold_last_7_days": row.units_sold,
            "average_daily_demand": round(
                float(average_daily_demand), 2
            ),
            "estimated_next_7_day_demand": predicted_demand,
            "forecast_method": "7-day historical average baseline",
        })

    return {
        "agent": "Demand Forecasting Module",
        "forecast_period_days": 7,
        "forecasts": forecasts,
        "note": (
            "Baseline estimate using the previous 7 days of sales. "
            "Insufficient sales history may limit accuracy."
        ),
    }


# 3. SALES INTELLIGENCE MODULE
def run_sales_intelligence_agent(
    db: Session,
    current_user,
    shop_id,
):
    overview = get_sales_overview(db, current_user, shop_id)

    top_products = get_top_selling_products(
        db,
        current_user,
        shop_id,
        limit=5,
    )

    return {
        "agent": "Sales Intelligence Module",
        "sales_overview": overview,
        "top_selling_products": top_products,
        "insights": [
            (
                f"Total revenue generated: "
                f"₹{overview['total_revenue']}"
            ),
            (
                f"Total orders processed: "
                f"{overview['total_orders']}"
            ),
            (
                f"Total units sold: "
                f"{overview['units_sold']}"
            ),
        ],
    }


# 4. BUSINESS RECOMMENDATIONS
def run_business_advisor_agent(
    db: Session,
    current_user,
    shop_id,
):
    inventory_report = run_inventory_agent(
        db, current_user, shop_id
    )

    sales_report = run_sales_intelligence_agent(
        db, current_user, shop_id
    )

    demand_report = run_demand_forecasting_agent(
        db, current_user, shop_id
    )

    recommendations = []

    for alert in inventory_report["alerts"]:
        recommendations.append({
            "category": "Inventory",
            "priority": alert["severity"],
            "recommendation": alert["recommendation"],
        })

    for forecast in demand_report["forecasts"]:
        if forecast["estimated_next_7_day_demand"] > 0:
            recommendations.append({
                "category": "Demand",
                "priority": "information",
                "recommendation": (
                    f"{forecast['product_name']} has an estimated "
                    f"7-day demand of "
                    f"{forecast['estimated_next_7_day_demand']} units."
                ),
            })

    return {
        "agent": "Business Recommendations",
        "generated_at": datetime.now().isoformat(),
        "inventory_report": inventory_report,
        "sales_report": sales_report,
        "demand_report": demand_report,
        "recommendations": recommendations,
    }
