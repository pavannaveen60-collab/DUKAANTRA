
import uuid
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import json
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from models.customer import Customer
from models.inventory import Inventory
from models.inventory_movement import InventoryMovement
from models.order import Order
from models.order_idempotency import OrderIdempotency
from models.order_item import OrderItem
from models.product import Product
from models.shop import Shop
from schemas.order import OrderCreate


ORDER_CREATE_OPERATION = "create_order"


class OrderIdempotencyConflict(ValueError):
    """Raised when an idempotency key is reused with a different payload."""


def _request_hash(order_data: OrderCreate) -> str:
    quantities: defaultdict[uuid.UUID, int] = defaultdict(int)
    for item in order_data.items:
        quantities[item.product_id] += item.quantity

    canonical_request = {
        "customer_id": (
            str(order_data.customer_id)
            if order_data.customer_id is not None
            else None
        ),
        "items": [
            {"product_id": str(product_id), "quantity": quantity}
            for product_id, quantity in sorted(
                quantities.items(),
                key=lambda item: str(item[0]),
            )
        ],
    }
    encoded_request = json.dumps(
        canonical_request,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded_request).hexdigest()


def _order_result(db: Session, order: Order):
    return {
        "id": order.id,
        "shop_id": order.shop_id,
        "customer_id": order.customer_id,
        "order_number": order.order_number,
        "status": order.status,
        "total_amount": order.total_amount,
        "created_at": order.created_at,
        "items": list(
            db.scalars(
                select(OrderItem).where(OrderItem.order_id == order.id)
            ).all()
        ),
    }


def _create_order_once(
    db: Session,
    current_user,
    shop_id: uuid.UUID,
    order_data: OrderCreate,
    idempotency_key: str,
):
    try:
        shop = db.scalar(
            select(Shop).where(
                Shop.id == shop_id,
                Shop.owner_id == current_user.id,
            )
        )
        if shop is None:
            raise ValueError("Shop not found or access denied.")

        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("A valid Idempotency-Key is required.")

        key_hash = sha256(idempotency_key.encode("utf-8")).hexdigest()
        request_hash = _request_hash(order_data)
        idempotency_record = OrderIdempotency(
            user_id=current_user.id,
            shop_id=shop.id,
            operation=ORDER_CREATE_OPERATION,
            key_hash=key_hash,
            request_hash=request_hash,
        )

        try:
            with db.begin_nested():
                db.add(idempotency_record)
                db.flush()
        except IntegrityError:
            db.rollback()
            existing_record = db.scalar(
                select(OrderIdempotency).where(
                    OrderIdempotency.user_id == current_user.id,
                    OrderIdempotency.shop_id == shop.id,
                    OrderIdempotency.operation == ORDER_CREATE_OPERATION,
                    OrderIdempotency.key_hash == key_hash,
                )
            )
            if existing_record is None:
                raise
            if existing_record.request_hash != request_hash:
                raise OrderIdempotencyConflict(
                    "Idempotency key was already used with a different order "
                    "request."
                ) from None
            if existing_record.order_id is None:
                raise OrderIdempotencyConflict(
                    "This order request is still being processed. Retry with "
                    "the same Idempotency-Key."
                ) from None

            existing_order = db.scalar(
                select(Order).where(
                    Order.id == existing_record.order_id,
                    Order.shop_id == shop.id,
                )
            )
            if existing_order is None:
                raise OrderIdempotencyConflict(
                    "The original order for this Idempotency-Key is no longer "
                    "available."
                ) from None
            return _order_result(db, existing_order)

        if order_data.customer_id is not None:
            customer = db.scalar(
                select(Customer).where(
                    Customer.id == order_data.customer_id,
                    Customer.shop_id == shop.id,
                )
            )
            if customer is None:
                raise ValueError("Customer not found in this shop.")

        requested_quantities = defaultdict(int)
        for item in order_data.items:
            requested_quantities[item.product_id] += item.quantity

        order_lines = []
        total_amount = Decimal("0.00")

        for product_id, quantity in sorted(
            requested_quantities.items(),
            key=lambda item: str(item[0]),
        ):
            product = db.scalar(
                select(Product).where(
                    Product.id == product_id,
                    Product.shop_id == shop.id,
                    Product.is_active.is_(True),
                )
            )
            if product is None:
                raise ValueError(f"Product {product_id} not found or inactive.")

            inventory = db.scalar(
                select(Inventory)
                .where(
                    Inventory.shop_id == shop.id,
                    Inventory.product_id == product.id,
                )
                .with_for_update()
            )
            if inventory is None:
                raise ValueError(f"Inventory not found for {product.name}.")

            if inventory.quantity < quantity:
                raise ValueError(
                    f"Insufficient stock for {product.name}. "
                    f"Available: {inventory.quantity}, requested: {quantity}."
                )

            unit_price = Decimal(str(product.price)).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            subtotal = (unit_price * quantity).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            total_amount += subtotal

            order_lines.append({
                "product": product,
                "inventory": inventory,
                "quantity": quantity,
                "unit_price": unit_price,
                "subtotal": subtotal,
            })

        order_number = (
            f"ORD-{datetime.now().strftime('%Y%m%d')}-"
            f"{uuid.uuid4().hex[:8].upper()}"
        )

        order = Order(
            id=uuid.uuid4(),
            shop_id=shop.id,
            customer_id=order_data.customer_id,
            order_number=order_number,
            status="confirmed",
            total_amount=total_amount,
        )
        db.add(order)
        db.flush()
        idempotency_record.order_id = order.id

        for line in order_lines:
            product = line["product"]
            inventory = line["inventory"]
            quantity = line["quantity"]

            db.add(
                OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=quantity,
                    unit_price=line["unit_price"],
                    subtotal=line["subtotal"],
                )
            )

            quantity_before = inventory.quantity
            inventory.quantity -= quantity

            db.add(
                InventoryMovement(
                    shop_id=shop.id,
                    product_id=product.id,
                    inventory_id=inventory.id,
                    user_id=current_user.id,
                    quantity_before=quantity_before,
                    quantity_change=-quantity,
                    quantity_after=inventory.quantity,
                    reason=f"Sale - Order {order_number}",
                    movement_type="reduction",
                )
            )

        db.commit()
        db.refresh(order)

        return _order_result(db, order)

    except Exception:
        db.rollback()
        raise


def create_order(
    db: Session,
    current_user,
    shop_id: uuid.UUID,
    order_data: OrderCreate,
    idempotency_key: str,
):
    for attempt in range(3):
        try:
            return _create_order_once(
                db,
                current_user,
                shop_id,
                order_data,
                idempotency_key,
            )
        except DBAPIError as error:
            db.rollback()
            sqlstate = getattr(error.orig, "sqlstate", None) or getattr(
                error.orig,
                "pgcode",
                None,
            )
            if sqlstate != "40001" or attempt == 2:
                raise


def get_shop_orders(
    db: Session,
    current_user,
    shop_id: uuid.UUID,
):
    shop = db.scalar(
        select(Shop).where(
            Shop.id == shop_id,
            Shop.owner_id == current_user.id,
        )
    )
    if shop is None:
        raise ValueError("Shop not found or access denied.")

    orders = list(
        db.scalars(
            select(Order)
            .where(Order.shop_id == shop.id)
            .order_by(Order.created_at.desc())
        ).all()
    )

    return [
        {
            "id": order.id,
            "shop_id": order.shop_id,
            "customer_id": order.customer_id,
            "order_number": order.order_number,
            "status": order.status,
            "total_amount": order.total_amount,
            "created_at": order.created_at,
            "items": list(
                db.scalars(
                    select(OrderItem).where(OrderItem.order_id == order.id)
                ).all()
            ),
        }
        for order in orders
    ]


def get_order_by_id(
    db: Session,
    current_user,
    shop_id: uuid.UUID,
    order_id: uuid.UUID,
):
    shop = db.scalar(
        select(Shop).where(
            Shop.id == shop_id,
            Shop.owner_id == current_user.id,
        )
    )
    if shop is None:
        raise ValueError("Shop not found or access denied.")

    order = db.scalar(
        select(Order).where(
            Order.id == order_id,
            Order.shop_id == shop.id,
        )
    )
    if order is None:
        return None

    return {
        "id": order.id,
        "shop_id": order.shop_id,
        "customer_id": order.customer_id,
        "order_number": order.order_number,
        "status": order.status,
        "total_amount": order.total_amount,
        "created_at": order.created_at,
        "items": list(
            db.scalars(
                select(OrderItem).where(OrderItem.order_id == order.id)
            ).all()
        ),
    }
