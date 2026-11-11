
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from core.dependencies import get_current_user
from models.user import User
from schemas.order import OrderCreate, OrderResponse
from services.order_service import (
    OrderIdempotencyConflict,
    create_order,
    get_shop_orders,
    get_order_by_id,
)

router = APIRouter(
    prefix="/shops/{shop_id}/orders",
    tags=["Orders & Sales"],
)


@router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_new_order(
    shop_id: UUID,
    order_data: OrderCreate,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=16,
        max_length=255,
        pattern=r"^\S+$",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return create_order(
            db,
            current_user,
            shop_id,
            order_data,
            idempotency_key,
        )
    except OrderIdempotencyConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from None
    except ValueError as error:
        message = str(error)
        error_status = (
            status.HTTP_409_CONFLICT
            if "Insufficient stock" in message
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=error_status,
            detail=message,
        )


@router.get("/", response_model=list[OrderResponse])
def list_orders(
    shop_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return get_shop_orders(db, current_user, shop_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        )


@router.get("/{order_id}", response_model=OrderResponse)
def retrieve_order(
    shop_id: UUID,
    order_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        order = get_order_by_id(db, current_user, shop_id, order_id)

        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found.",
            )

        return order

    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        )
