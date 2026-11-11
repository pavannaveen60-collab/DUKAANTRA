
import time
import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from core.dependencies import get_current_user
from database import get_db
from models.inventory import Inventory
from models.order import Order
from models.product import Product
from models.shop import Shop
from models.user import User
from services.gemini_service import (
    ask_gemini,
    GeminiEmptyResponseError,
    GeminiQuotaError,
    GeminiServiceError,
    GeminiTimeoutError,
)


router = APIRouter(
    prefix="/shops/{shop_id}/ai",
    tags=["DUKAANTRA Gemini AI"],
)

logger = logging.getLogger("dukaantra.ai")


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(
        default_factory=list,
        max_length=8,
    )


@router.post("/chat")
async def chat_with_dukaantra(
    shop_id: UUID,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Check Gemini configuration
    if not settings.GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Gemini API key is not configured.",
        )

    # Verify shop ownership
    shop = db.scalar(
        select(Shop).where(
            Shop.id == shop_id,
            Shop.owner_id == current_user.id,
        )
    )

    if shop is None:
        raise HTTPException(
            status_code=404,
            detail="Shop not found.",
        )

    # FAST RESPONSE: Handle simple greetings without Gemini
    greeting = payload.message.strip().lower().strip("!.,? ")

    greetings = {
        "hi",
        "hello",
        "hey",
        "hii",
        "hiii",
        "good morning",
        "good afternoon",
        "good evening",
        "how are you",
    }

    if greeting in greetings:
        return {
            "success": True,
            "assistant": "DUKAANTRA AI",
            "reply": (
                f"Hello! Welcome to {shop.shop_name}. "
                "How can I help you with your business today?"
            ),
            "context_scope": "Greeting response",
        }

    # Start measuring database and context preparation time
    request_start = time.perf_counter()

    # Fetch active products and inventory
    product_rows = db.execute(
        select(Product, Inventory)
        .outerjoin(
            Inventory,
            (Inventory.product_id == Product.id)
            & (Inventory.shop_id == shop.id),
        )
        .where(
            Product.shop_id == shop.id,
            Product.is_active.is_(True),
        )
        .order_by(Product.name)
        .limit(150)
    ).all()

    products = [
        {
            "name": product.name,
            "category": product.category,
            "price_inr": str(product.price),
            "stock": inventory.quantity if inventory else 0,
            "low_stock_threshold": (
                inventory.low_stock_threshold if inventory else None
            ),
            "sku": product.sku,
        }
        for product, inventory in product_rows
    ]

    # Fetch latest 20 orders
    recent_orders = db.scalars(
        select(Order)
        .where(Order.shop_id == shop.id)
        .order_by(Order.created_at.desc())
        .limit(20)
    ).all()

    orders = [
        {
            "order_number": order.order_number,
            "status": order.status,
            "total_inr": str(order.total_amount),
            "created_at": order.created_at.isoformat(),
        }
        for order in recent_orders
    ]

    confirmed_orders = [
        order
        for order in recent_orders
        if order.status == "confirmed"
    ]

    # Prepare shop business context
    context = {
        "shop": {
            "name": shop.shop_name,
            "business_type": shop.business_type,
            "city": shop.city,
            "state": shop.state,
        },
        "inventory_summary": {
            "active_product_count": len(products),
            "total_units_in_stock": sum(
                product["stock"] for product in products
            ),
            "low_stock_products": [
                product
                for product in products
                if product["low_stock_threshold"] is not None
                and product["stock"]
                <= product["low_stock_threshold"]
            ],
        },
        "products": products,
        "recent_orders": orders,
        "recent_orders_count": len(recent_orders),
        "recent_confirmed_order_revenue_inr": str(
            sum(
                (order.total_amount for order in confirmed_orders),
                start=0,
            )
        ),
        "order_data_scope": (
            "Latest 20 orders only; not lifetime totals."
        ),
    }

    history = [
        item.model_dump()
        for item in payload.history
    ]

    try:
        # Database/context preparation timing
        print(
            "[DUKAANTRA AI] Database/context preparation: "
            f"{time.perf_counter() - request_start:.2f}s"
        )

        # Gemini response timing
        gemini_start = time.perf_counter()

        answer = await ask_gemini(
            payload.message,
            context,
            history,
        )

        print(
            "[DUKAANTRA AI] Gemini response: "
            f"{time.perf_counter() - gemini_start:.2f}s"
        )

    except GeminiQuotaError as error:
        raise HTTPException(status_code=503, detail=str(error)) from None
    except GeminiTimeoutError as error:
        raise HTTPException(status_code=504, detail=str(error)) from None
    except GeminiEmptyResponseError as error:
        raise HTTPException(status_code=502, detail=str(error)) from None
    except GeminiServiceError:
        raise HTTPException(
            status_code=502,
            detail=(
                "The AI assistant could not complete the request. "
                "Please try again later."
            ),
        ) from None
    except Exception as error:
        logger.error(
            "Gemini chat failed with error type %s.",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "The AI assistant could not complete the request. "
                "Check Gemini configuration and service availability."
            ),
        )

    return {
        "success": True,
        "assistant": "DUKAANTRA AI",
        "reply": answer,
        "context_scope": (
            "Current shop inventory and latest 20 orders"
        ),
    }
