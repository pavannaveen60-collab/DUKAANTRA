
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class InventoryMovementResponse(BaseModel):
    id: UUID
    shop_id: UUID
    product_id: UUID
    inventory_id: UUID
    user_id: UUID | None = None

    quantity_before: int
    quantity_change: int
    quantity_after: int

    reason: str
    movement_type: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
