
from uuid import UUID

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ShopCreate(BaseModel):
    shop_name: str = Field(min_length=2, max_length=150)
    business_type: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=7, max_length=20)
    address: str = Field(min_length=3, max_length=500)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    pincode: str | None = Field(default=None, max_length=10)

    @field_validator("shop_name", "business_type", "address", mode="before")
    @classmethod
    def trim_required_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("phone", mode="before")
    @classmethod
    def normalize_phone(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        normalized = value.strip()
        digits = "".join(character for character in normalized if character.isdigit())
        if len(digits) < 7 or len(digits) > 15:
            raise ValueError("Enter a valid phone number.")
        if any(not (character.isdigit() or character in "+()- .") for character in normalized):
            raise ValueError("Enter a valid phone number.")
        return normalized


class ShopUpdate(BaseModel):
    shop_name: str | None = Field(default=None, min_length=2, max_length=150)
    business_type: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, min_length=7, max_length=20)
    address: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    pincode: str | None = Field(default=None, max_length=10)


class ShopResponse(BaseModel):
    id: UUID
    owner_id: UUID
    shop_name: str
    business_type: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None

    model_config = ConfigDict(from_attributes=True)
