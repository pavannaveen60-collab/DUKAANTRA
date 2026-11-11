from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InventoryCreate(BaseModel):
    product_id: UUID
    quantity: int = Field(default=0, ge=0)
    low_stock_threshold: int = Field(default=5, ge=0)


class InventoryUpdate(BaseModel):
    quantity: int | None = Field(default=None, ge=0)
    low_stock_threshold: int | None = Field(default=None, ge=0)


class StockAdjustment(BaseModel):
    quantity_change: int
    reason: str = Field(min_length=2, max_length=255)


class InventoryResponse(BaseModel):
    id: UUID
    shop_id: UUID
    product_id: UUID
    quantity: int
    low_stock_threshold: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)