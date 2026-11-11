from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from schemas.shop import ShopCreate, ShopUpdate, ShopResponse
from services.shop_service import (
    create_shop,
    get_my_shops,
    get_shop_by_id,
    update_shop,
)
from core.dependencies import get_current_user


router = APIRouter(
    prefix="/shops",
    tags=["Shops"]
)


@router.post(
    "/",
    response_model=ShopResponse,
    status_code=status.HTTP_201_CREATED
)
def create_new_shop(
    shop_data: ShopCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return create_shop(db, current_user, shop_data)


@router.get(
    "/",
    response_model=list[ShopResponse]
)
def list_my_shops(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return get_my_shops(db, current_user)


@router.get(
    "/{shop_id}",
    response_model=ShopResponse
)
def retrieve_shop(
    shop_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    shop = get_shop_by_id(db, current_user, shop_id)

    if shop is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found"
        )

    return shop


@router.patch(
    "/{shop_id}",
    response_model=ShopResponse
)
def edit_shop(
    shop_id: UUID,
    shop_data: ShopUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    shop = get_shop_by_id(db, current_user, shop_id)

    if shop is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found"
        )

    if (
        "shop_name" in shop_data.model_fields_set
        and shop_data.shop_name is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Shop name cannot be empty"
        )

    return update_shop(db, shop, shop_data)