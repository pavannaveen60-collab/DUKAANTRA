from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    sku: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=1000)

    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    cost_price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2
    )


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    sku: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=1000)

    price: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=2
    )

    cost_price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2
    )

    is_active: bool | None = None


class ProductResponse(BaseModel):
    id: UUID
    shop_id: UUID
    name: str
    sku: str | None = None
    category: str | None = None
    description: str | None = None
    price: Decimal
    cost_price: Decimal | None = None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)