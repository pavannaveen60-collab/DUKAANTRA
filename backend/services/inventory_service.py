
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.inventory import Inventory
from models.inventory_movement import InventoryMovement
from models.product import Product
from models.shop import Shop
from models.user import User

from schemas.inventory import (
    InventoryCreate,
    InventoryUpdate,
    StockAdjustment,
)


def verify_shop_ownership(db, current_user, shop_id):
    return db.scalar(
        select(Shop).where(
            Shop.id == shop_id,
            Shop.owner_id == current_user.id,
        )
    )


def create_inventory(db, current_user, shop_id, inventory_data):
    shop = verify_shop_ownership(db, current_user, shop_id)

    if shop is None:
        raise ValueError("Shop not found or access denied.")

    product = db.scalar(
        select(Product).where(
            Product.id == inventory_data.product_id,
            Product.shop_id == shop.id,
        )
    )

    if product is None:
        raise ValueError("Product not found in this shop.")

    existing = db.scalar(
        select(Inventory).where(
            Inventory.shop_id == shop.id,
            Inventory.product_id == product.id,
        )
    )

    if existing:
        raise ValueError("Inventory already exists for this product.")

    inventory = Inventory(
        shop_id=shop.id,
        product_id=product.id,
        quantity=inventory_data.quantity,
        low_stock_threshold=inventory_data.low_stock_threshold,
    )

    try:
        db.add(inventory)
        db.flush()

        if inventory.quantity > 0:
            db.add(
                InventoryMovement(
                    shop_id=shop.id,
                    product_id=product.id,
                    inventory_id=inventory.id,
                    user_id=current_user.id,
                    quantity_before=0,
                    quantity_change=inventory.quantity,
                    quantity_after=inventory.quantity,
                    reason="Initial stock entry",
                    movement_type="addition",
                )
            )

        db.commit()
        db.refresh(inventory)
        return inventory

    except Exception:
        db.rollback()
        raise


def get_shop_inventory(db, current_user, shop_id):
    shop = verify_shop_ownership(db, current_user, shop_id)

    if shop is None:
        raise ValueError("Shop not found or access denied.")

    statement = (
        select(Inventory)
        .where(Inventory.shop_id == shop.id)
        .order_by(Inventory.updated_at.desc())
    )

    return list(db.scalars(statement).all())


def get_inventory_by_id(db, current_user, shop_id, inventory_id):
    shop = verify_shop_ownership(db, current_user, shop_id)

    if shop is None:
        return None

    return db.scalar(
        select(Inventory).where(
            Inventory.id == inventory_id,
            Inventory.shop_id == shop.id,
        )
    )


def update_inventory(
    db,
    inventory,
    inventory_data,
    current_user,
):
    update_data = inventory_data.model_dump(
        exclude_unset=True
    )

    try:
        statement = (
            select(Inventory)
            .where(Inventory.id == inventory.id)
            .with_for_update()
        )

        locked_inventory = db.scalar(statement)

        if locked_inventory is None:
            raise ValueError("Inventory record not found.")

        if "quantity" in update_data:
            new_quantity = update_data.pop("quantity")
            reason = update_data.pop("reason", None)

            if new_quantity is None:
                raise ValueError("Quantity cannot be null.")

            previous_quantity = locked_inventory.quantity
            quantity_change = new_quantity - previous_quantity

            if quantity_change != 0:
                if not reason:
                    reason = "Manual inventory update"

                movement = InventoryMovement(
                    shop_id=locked_inventory.shop_id,
                    product_id=locked_inventory.product_id,
                    inventory_id=locked_inventory.id,
                    user_id=current_user.id,
                    quantity_before=previous_quantity,
                    quantity_change=quantity_change,
                    quantity_after=new_quantity,
                    reason=reason,
                    movement_type=(
                        "addition"
                        if quantity_change > 0
                        else "reduction"
                    ),
                )

                db.add(movement)

            locked_inventory.quantity = new_quantity

        else:
            update_data.pop("reason", None)

        for field, value in update_data.items():
            setattr(locked_inventory, field, value)

        db.commit()
        db.refresh(locked_inventory)
        return locked_inventory

    except Exception:
        db.rollback()
        raise


def adjust_stock(db, inventory, adjustment, current_user):
    if adjustment.quantity_change == 0:
        raise ValueError("Stock adjustment cannot be zero.")

    try:
        locked_inventory = db.scalar(
            select(Inventory)
            .where(Inventory.id == inventory.id)
            .with_for_update()
        )

        if locked_inventory is None:
            raise ValueError("Inventory record not found.")

        previous_quantity = locked_inventory.quantity
        new_quantity = previous_quantity + adjustment.quantity_change

        if new_quantity < 0:
            raise ValueError(
                "Insufficient stock. Quantity cannot be negative."
            )

        locked_inventory.quantity = new_quantity

        db.add(
            InventoryMovement(
                shop_id=locked_inventory.shop_id,
                product_id=locked_inventory.product_id,
                inventory_id=locked_inventory.id,
                user_id=current_user.id,
                quantity_before=previous_quantity,
                quantity_change=adjustment.quantity_change,
                quantity_after=new_quantity,
                reason=adjustment.reason,
                movement_type=(
                    "addition"
                    if adjustment.quantity_change > 0
                    else "reduction"
                ),
            )
        )

        db.commit()
        db.refresh(locked_inventory)
        return locked_inventory

    except Exception:
        db.rollback()
        raise


def get_low_stock_inventory(db, current_user, shop_id):
    shop = verify_shop_ownership(db, current_user, shop_id)

    if shop is None:
        raise ValueError("Shop not found or access denied.")

    statement = (
        select(Inventory)
        .where(
            Inventory.shop_id == shop.id,
            Inventory.quantity <= Inventory.low_stock_threshold,
        )
        .order_by(Inventory.quantity.asc())
    )

    return list(db.scalars(statement).all())
