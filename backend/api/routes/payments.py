import uuid
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from core.dependencies import get_current_user
from models.user import User
from models.shop import Shop
from models.customer import Customer
from models.product import Product
from models.inventory import Inventory
from models.order import Order
from models.order_item import OrderItem
from models.payment import Payment
from schemas.order import OrderCreate
from services.exchange_rate_service import (
    get_inr_to_usd_rate,
    convert_inr_to_usd,
    ExchangeRateError,
)
from payments.paypal_service import (
    create_paypal_order,
    PayPalAPIError,
)


router = APIRouter(
    prefix="/shops/{shop_id}/payments",
    tags=["Payments"],
)


@router.post("/checkout", status_code=status.HTTP_201_CREATED)
async def create_checkout(
    shop_id: uuid.UUID,
    order_data: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify shop ownership.
    shop = db.scalar(
        select(Shop).where(
            Shop.id == shop_id,
            Shop.owner_id == current_user.id,
        )
    )
    if shop is None:
        raise HTTPException(404, "Shop not found or access denied.")

    if not order_data.items:
        raise HTTPException(400, "At least one order item is required.")

    # Verify customer belongs to this shop.
    if order_data.customer_id is not None:
        customer = db.scalar(
            select(Customer).where(
                Customer.id == order_data.customer_id,
                Customer.shop_id == shop.id,
            )
        )
        if customer is None:
            raise HTTPException(400, "Customer not found in this shop.")

    # Combine duplicate product lines.
    requested = defaultdict(int)
    for item in order_data.items:
        if item.quantity <= 0:
            raise HTTPException(400, "Quantity must be greater than zero.")
        requested[item.product_id] += item.quantity

    # Validate products and stock. This is an availability check;
    # stock is checked again under lock during capture.
    lines = []
    total_inr = Decimal("0.00")

    try:
        for product_id, quantity in requested.items():
            product = db.scalar(
                select(Product).where(
                    Product.id == product_id,
                    Product.shop_id == shop.id,
                    Product.is_active.is_(True),
                )
            )
            if product is None:
                raise HTTPException(400, f"Product {product_id} not found or inactive.")

            inventory = db.scalar(
                select(Inventory).where(
                    Inventory.shop_id == shop.id,
                    Inventory.product_id == product.id,
                )
            )
            if inventory is None:
                raise HTTPException(409, f"Inventory not found for {product.name}.")

            if inventory.quantity < quantity:
                raise HTTPException(
                    409,
                    f"Insufficient stock for {product.name}. "
                    f"Available: {inventory.quantity}, requested: {quantity}.",
                )

            unit_price = Decimal(str(product.price)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            subtotal = (unit_price * quantity).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            total_inr += subtotal

            lines.append({
                "product_id": product.id,
                "quantity": quantity,
                "unit_price": unit_price,
                "subtotal": subtotal,
            })

        if total_inr <= 0:
            raise HTTPException(400, "Order total must be greater than zero.")

        # Obtain the published exchange-rate snapshot.
        rate_data = await get_inr_to_usd_rate()
        amount_usd = convert_inr_to_usd(total_inr, rate_data.rate)

        if amount_usd <= 0:
            raise HTTPException(
                400,
                "Order is too small to process in USD.",
            )

        rate_timestamp = datetime.strptime(
            rate_data.updated_at,
            "%a, %d %b %Y %H:%M:%S %z",
        )

        order_number = (
            f"ORD-{datetime.now().strftime('%Y%m%d')}-"
            f"{uuid.uuid4().hex[:8].upper()}"
        )

        order = Order(
            shop_id=shop.id,
            customer_id=order_data.customer_id,
            order_number=order_number,
            status="pending_payment",
            total_amount=total_inr,
        )
        db.add(order)
        db.flush()

        for line in lines:
            db.add(
                OrderItem(
                    order_id=order.id,
                    product_id=line["product_id"],
                    quantity=line["quantity"],
                    unit_price=line["unit_price"],
                    subtotal=line["subtotal"],
                )
            )

        payment = Payment(
            shop_id=shop.id,
            order_id=order.id,
            provider="paypal",
            amount=amount_usd,
            currency="USD",
            source_amount_inr=total_inr,
            exchange_rate=rate_data.rate,
            exchange_rate_provider=rate_data.provider,
            exchange_rate_updated_at=rate_timestamp,
            status="creating",
        )
        db.add(payment)
        db.commit()
        db.refresh(order)
        db.refresh(payment)

    except HTTPException:
        db.rollback()
        raise
    except ExchangeRateError as error:
        db.rollback()
        raise HTTPException(503, str(error))
    except Exception:
        db.rollback()
        raise

    # Create the PayPal order after the internal records are committed.
    try:
        paypal_result = await create_paypal_order(
            amount_usd=payment.amount,
            reference_id=order.order_number,
            custom_id=str(order.id),
            request_id=payment.id.hex,
        )

        payment.provider_order_id = paypal_result["id"]
        payment.status = "pending"
        db.commit()

    except PayPalAPIError:
        db.rollback()
        payment = db.get(Payment, payment.id)
        order = db.get(Order, order.id)

        if payment:
            payment.status = "creation_failed"
        if order:
            order.status = "payment_failed"

        db.commit()
        raise HTTPException(
            502,
            "PayPal could not create the checkout. No payment was captured.",
        )

    return {
        "order_id": str(order.id),
        "order_number": order.order_number,
        "order_status": order.status,
        "payment_id": str(payment.id),
        "payment_status": payment.status,
        "source_amount_inr": str(total_inr),
        "amount_usd": str(amount_usd),
        "currency": "USD",
        "exchange_rate": str(rate_data.rate),
        "exchange_rate_description": "1 INR = USD " + str(rate_data.rate),
        "exchange_rate_provider": rate_data.provider,
        "exchange_rate_updated_at": rate_data.updated_at,
        "paypal_order_id": paypal_result["id"],
        "approval_url": paypal_result["approval_url"],
    }
