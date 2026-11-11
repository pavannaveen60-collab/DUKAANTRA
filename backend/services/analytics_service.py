
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.order import Order
from models.order_item import OrderItem
from models.product import Product
from models.shop import Shop


def verify_shop_ownership(db: Session, current_user, shop_id):
    shop = db.scalar(
        select(Shop).where(
            Shop.id == shop_id,
            Shop.owner_id == current_user.id,
        )
    )

    if shop is None:
        raise ValueError("Shop not found or access denied.")

    return shop


def get_sales_overview(db: Session, current_user, shop_id):
    verify_shop_ownership(db, current_user, shop_id)

    result = db.execute(
        select(
            func.count(Order.id),
            func.coalesce(func.sum(Order.total_amount), 0),
        ).where(
            Order.shop_id == shop_id,
            Order.status == "confirmed",
        )
    ).one()

    total_orders = result[0]
    total_revenue = Decimal(str(result[1]))

    units_sold = db.scalar(
        select(func.coalesce(func.sum(OrderItem.quantity), 0))
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.shop_id == shop_id,
            Order.status == "confirmed",
        )
    ) or 0

    average_order_value = (
        total_revenue / total_orders
        if total_orders
        else Decimal("0.00")
    )

    return {
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "units_sold": units_sold,
        "average_order_value": average_order_value.quantize(
            Decimal("0.01")
        ),
    }


def get_daily_sales(db: Session, current_user, shop_id, days=7):
    verify_shop_ownership(db, current_user, shop_id)

    start_date = date.today() - timedelta(days=days - 1)
    start_datetime = datetime.combine(start_date, time.min)

    results = db.execute(
        select(
            func.date(Order.created_at).label("sale_date"),
            func.count(Order.id).label("orders"),
            func.coalesce(func.sum(Order.total_amount), 0).label("revenue"),
        )
        .where(
            Order.shop_id == shop_id,
            Order.status == "confirmed",
            Order.created_at >= start_datetime,
        )
        .group_by(func.date(Order.created_at))
        .order_by(func.date(Order.created_at))
    ).all()

    return [
        {
            "date": row.sale_date,
            "orders": row.orders,
            "revenue": Decimal(str(row.revenue)),
        }
        for row in results
    ]


def get_monthly_sales(db: Session, current_user, shop_id, months=6):
    verify_shop_ownership(db, current_user, shop_id)

    start_date = date.today().replace(day=1)
    for _ in range(months - 1):
        start_date = (
            start_date.replace(day=1) - timedelta(days=1)
        ).replace(day=1)

    start_datetime = datetime.combine(start_date, time.min)

    month_label = func.to_char(Order.created_at, "YYYY-MM")

    results = db.execute(
        select(
            month_label.label("month"),
            func.count(Order.id).label("orders"),
            func.coalesce(func.sum(Order.total_amount), 0).label("revenue"),
        )
        .where(
            Order.shop_id == shop_id,
            Order.status == "confirmed",
            Order.created_at >= start_datetime,
        )
        .group_by(month_label)
        .order_by(month_label)
    ).all()

    return [
        {
            "month": row.month,
            "orders": row.orders,
            "revenue": Decimal(str(row.revenue)),
        }
        for row in results
    ]


def get_top_selling_products(
    db: Session,
    current_user,
    shop_id,
    limit=5,
):
    verify_shop_ownership(db, current_user, shop_id)

    results = db.execute(
        select(
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            func.sum(OrderItem.quantity).label("units_sold"),
            func.sum(OrderItem.subtotal).label("revenue"),
        )
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.shop_id == shop_id,
            Order.status == "confirmed",
            Product.shop_id == shop_id,
        )
        .group_by(Product.id, Product.name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(limit)
    ).all()

    return [
        {
            "product_id": row.product_id,
            "product_name": row.product_name,
            "units_sold": row.units_sold,
            "revenue": Decimal(str(row.revenue)),
        }
        for row in results
    ]
