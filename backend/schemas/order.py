
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OrderItemCreate(BaseModel):
    product_id: UUID
    quantity: int = Field(gt=0, le=10000)


class OrderCreate(BaseModel):
    customer_id: UUID | None = None
    items: list[OrderItemCreate] = Field(min_length=1, max_length=100)


class OrderItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    quantity: int
    unit_price: Decimal
    subtotal: Decimal

    model_config = ConfigDict(from_attributes=True)


class OrderResponse(BaseModel):
    id: UUID
    shop_id: UUID
    customer_id: UUID | None = None
    order_number: str
    status: str
    total_amount: Decimal
    created_at: datetime
    items: list[OrderItemResponse] = []

    model_config = ConfigDict(from_attributes=True)


class OrderStatusUpdate(BaseModel):
    status: str = Field(
        min_length=3,
        max_length=30,
        pattern=r"^(pending|confirmed|completed|cancelled)$"
    )
