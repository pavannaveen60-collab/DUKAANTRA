from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from schemas.product import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
)
from services.product_service import (
    create_product,
    get_shop_products,
    get_product_by_id,
    update_product,
)
from core.dependencies import get_current_user


router = APIRouter(
    prefix="/shops/{shop_id}/products",
    tags=["Products"]
)


@router.post(
    "/",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED
)
def add_product(
    shop_id: UUID,
    product_data: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        return create_product(
            db,
            current_user,
            shop_id,
            product_data
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error)
        )


@router.get(
    "/",
    response_model=list[ProductResponse]
)
def list_products(
    shop_id: UUID,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        return get_shop_products(
            db,
            current_user,
            shop_id,
            include_inactive
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error)
        )


@router.get(
    "/{product_id}",
    response_model=ProductResponse
)
def retrieve_product(
    shop_id: UUID,
    product_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    product = get_product_by_id(
        db,
        current_user,
        shop_id,
        product_id
    )

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product or shop not found."
        )

    return product


@router.patch(
    "/{product_id}",
    response_model=ProductResponse
)
def edit_product(
    shop_id: UUID,
    product_id: UUID,
    product_data: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    product = get_product_by_id(
        db,
        current_user,
        shop_id,
        product_id
    )

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product or shop not found."
        )

    try:
        return update_product(db, product, product_data)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error)
        )