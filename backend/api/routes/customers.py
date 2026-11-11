
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.user import User

from schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
)

from services.customer_service import (
    create_customer,
    get_shop_customers,
    get_customer_by_id,
    update_customer,
    delete_customer,
)

from core.dependencies import get_current_user


router = APIRouter(
    prefix="/shops/{shop_id}/customers",
    tags=["Customers"],
)


@router.post(
    "/",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_customer(
    shop_id: UUID,
    customer_data: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return create_customer(
            db, current_user, shop_id, customer_data
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.get("/", response_model=list[CustomerResponse])
def list_customers(
    shop_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return get_shop_customers(db, current_user, shop_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.get("/{customer_id}", response_model=CustomerResponse)
def retrieve_customer(
    shop_id: UUID,
    customer_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    customer = get_customer_by_id(
        db, current_user, shop_id, customer_id
    )

    if customer is None:
        raise HTTPException(
            status_code=404,
            detail="Customer not found.",
        )

    return customer


@router.patch("/{customer_id}", response_model=CustomerResponse)
def edit_customer(
    shop_id: UUID,
    customer_id: UUID,
    customer_data: CustomerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    customer = get_customer_by_id(
        db, current_user, shop_id, customer_id
    )

    if customer is None:
        raise HTTPException(
            status_code=404,
            detail="Customer not found.",
        )

    try:
        return update_customer(db, customer, customer_data)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.delete("/{customer_id}")
def remove_customer(
    shop_id: UUID,
    customer_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    customer = get_customer_by_id(
        db, current_user, shop_id, customer_id
    )

    if customer is None:
        raise HTTPException(
            status_code=404,
            detail="Customer not found.",
        )

    try:
        return delete_customer(db, customer)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))
