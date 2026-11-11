import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from core.dependencies import get_current_user

from models.user import User
from models.shop import Shop
from models.payment import Payment
from models.order import Order
from models.order_item import OrderItem
from models.inventory import Inventory
from models.inventory_movement import InventoryMovement

from payments.paypal_service import (
    capture_paypal_order,
    PayPalAPIError,
)

router = APIRouter(
    prefix="/shops/{shop_id}/payments",
    tags=["Payments"],
)


@router.post("/{payment_id}/capture")
async def capture_payment(
    shop_id: uuid.UUID,
    payment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        # 1. Verify shop ownership.
        shop = db.scalar(
            select(Shop).where(
                Shop.id == shop_id,
                Shop.owner_id == current_user.id,
            )
        )

        if shop is None:
            raise HTTPException(
                status_code=404,
                detail="Shop not found or access denied.",
            )

        # 2. Lock the payment row to prevent duplicate captures.
        payment = db.scalar(
            select(Payment)
            .where(
                Payment.id == payment_id,
                Payment.shop_id == shop.id,
            )
            .with_for_update()
        )

        if payment is None:
            raise HTTPException(
                status_code=404,
                detail="Payment not found.",
            )

        # Idempotent response for an already completed payment.
        if payment.status == "completed":
            return {
                "success": True,
                "message": "Payment was already completed.",
                "payment_id": str(payment.id),
                "capture_id": payment.provider_capture_id,
                "status": payment.status,
            }

        if payment.provider != "paypal":
            raise HTTPException(
                status_code=400,
                detail="Unsupported payment provider.",
            )

        if payment.status != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"Payment cannot be captured. Current status: {payment.status}",
            )

        if not payment.provider_order_id:
            raise HTTPException(
                status_code=400,
                detail="PayPal order ID is missing.",
            )

        if payment.currency != "USD":
            raise HTTPException(
                status_code=400,
                detail="This PayPal integration requires USD payments.",
            )

        # 3. Lock the associated order.
        order = db.scalar(
            select(Order)
            .where(
                Order.id == payment.order_id,
                Order.shop_id == shop.id,
            )
            .with_for_update()
        )

        if order is None:
            raise HTTPException(
                status_code=404,
                detail="Associated order not found.",
            )

        if order.status != "pending_payment":
            raise HTTPException(
                status_code=409,
                detail=f"Order cannot be paid. Current status: {order.status}",
            )

        # 4. Load order items.
        order_items = list(
            db.scalars(
                select(OrderItem)
                .where(OrderItem.order_id == order.id)
                .order_by(OrderItem.product_id)
            ).all()
        )

        if not order_items:
            raise HTTPException(
                status_code=400,
                detail="Order has no items.",
            )

        # 5. Lock and validate all inventory rows before capturing.
        inventory_records = []

        for item in order_items:
            inventory = db.scalar(
                select(Inventory)
                .where(
                    Inventory.shop_id == shop.id,
                    Inventory.product_id == item.product_id,
                )
                .with_for_update()
            )

            if inventory is None:
                payment.status = "stock_unavailable"
                order.status = "payment_failed"
                db.commit()

                raise HTTPException(
                    status_code=409,
                    detail=f"Inventory record missing for product {item.product_id}. Payment was not captured.",
                )

            if inventory.quantity < item.quantity:
                available = inventory.quantity

                payment.status = "stock_unavailable"
                order.status = "payment_failed"
                db.commit()

                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Insufficient stock for product {item.product_id}. "
                        f"Available: {available}, requested: {item.quantity}. "
                        "Payment was not captured."
                    ),
                )

            inventory_records.append((item, inventory))

        # 6. Capture payment with a deterministic idempotency key.
        capture_request_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"dukaantra-capture-{payment.id}",
            )
        )

        try:
            capture_result = await capture_paypal_order(
                payment.provider_order_id,
                request_id=capture_request_id,
            )
        except PayPalAPIError as error:
            db.rollback()

            raise HTTPException(
                status_code=502,
                detail=(
                    "PayPal capture could not be confirmed. "
                    "Payment remains pending; retry safely before creating another payment. "
                    f"Provider detail: {str(error)[:300]}"
                ),
            )
        except Exception:
            db.rollback()

            raise HTTPException(
                status_code=502,
                detail=(
                    "PayPal capture could not be confirmed due to a communication error. "
                    "Payment remains pending. Retry using the same payment ID."
                ),
            )

        # 7. Verify PayPal's actual capture response.
        purchase_units = capture_result.get("purchase_units") or []

        if not purchase_units:
            db.rollback()
            raise HTTPException(
                status_code=502,
                detail="PayPal returned no purchase unit. Payment was not confirmed.",
            )

        payments_data = purchase_units[0].get("payments") or {}
        captures = payments_data.get("captures") or []

        if not captures:
            db.rollback()
            raise HTTPException(
                status_code=502,
                detail="PayPal returned no capture record.",
            )

        capture = captures[0]
        capture_amount = capture.get("amount") or {}

        if capture.get("status") != "COMPLETED":
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="PayPal has not confirmed a completed capture.",
            )

        if capture_amount.get("currency_code") != "USD":
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="PayPal capture currency does not match USD.",
            )

        try:
            captured_amount = Decimal(str(capture_amount["value"]))
        except (KeyError, ValueError, TypeError):
            db.rollback()
            raise HTTPException(
                status_code=502,
                detail="PayPal returned an invalid capture amount.",
            )

        if captured_amount != Decimal(str(payment.amount)):
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="Captured amount does not match the recorded payment amount.",
            )

        capture_id = capture.get("id")

        if not capture_id:
            db.rollback()
            raise HTTPException(
                status_code=502,
                detail="PayPal capture ID is missing.",
            )

        # 8. Payment is confirmed. Now deduct inventory.
        for item, inventory in inventory_records:
            quantity_before = inventory.quantity
            inventory.quantity -= item.quantity

            db.add(
                InventoryMovement(
                    shop_id=shop.id,
                    product_id=item.product_id,
                    inventory_id=inventory.id,
                    user_id=current_user.id,
                    quantity_before=quantity_before,
                    quantity_change=-item.quantity,
                    quantity_after=inventory.quantity,
                    reason=f"PayPal sale - Order {order.order_number}",
                    movement_type="reduction",
                )
            )

        # 9. Update payment and order atomically.
        payment.provider_capture_id = capture_id
        payment.status = "completed"

        order.status = "confirmed"

        db.commit()
        db.refresh(payment)
        db.refresh(order)

        return {
            "success": True,
            "message": "PayPal payment captured and order confirmed.",
            "payment_id": str(payment.id),
            "order_id": str(order.id),
            "order_number": order.order_number,
            "capture_id": capture_id,
            "amount_usd": str(payment.amount),
            "currency": payment.currency,
            "payment_status": payment.status,
            "order_status": order.status,
            "inventory_updated": True,
        }

    except HTTPException:
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while processing the payment.",
        )
