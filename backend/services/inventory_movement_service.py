
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.inventory import Inventory
from models.inventory_movement import InventoryMovement
from models.shop import Shop
from models.user import User


def get_inventory_movements(
    db: Session,
    current_user: User,
    shop_id: UUID,
    inventory_id: UUID,
) -> list[InventoryMovement]:
    """Retrieve movement history for an inventory record."""

    # Verify that the authenticated user owns this shop.
    shop = db.scalar(
        select(Shop).where(
            Shop.id == shop_id,
            Shop.owner_id == current_user.id,
        )
    )

    if shop is None:
        raise ValueError("Shop not found or access denied.")

    # Verify that the inventory record belongs to this shop.
    inventory = db.scalar(
        select(Inventory).where(
            Inventory.id == inventory_id,
            Inventory.shop_id == shop.id,
        )
    )

    if inventory is None:
        raise ValueError("Inventory record not found.")

    # Retrieve the movement history, newest first.
    statement = (
        select(InventoryMovement)
        .where(
            InventoryMovement.shop_id == shop.id,
            InventoryMovement.inventory_id == inventory.id,
        )
        .order_by(InventoryMovement.created_at.desc())
    )

    return list(db.scalars(statement).all())
