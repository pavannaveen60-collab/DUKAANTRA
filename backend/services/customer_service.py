
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.customer import Customer
from models.order import Order
from models.shop import Shop
from models.user import User

from schemas.customer import CustomerCreate, CustomerUpdate


def verify_shop_ownership(
    db: Session,
    current_user: User,
    shop_id: UUID,
):
    return db.scalar(
        select(Shop).where(
            Shop.id == shop_id,
            Shop.owner_id == current_user.id,
        )
    )


def create_customer(
    db: Session,
    current_user: User,
    shop_id: UUID,
    customer_data: CustomerCreate,
):
    shop = verify_shop_ownership(db, current_user, shop_id)

    if shop is None:
        raise ValueError("Shop not found or access denied.")

    customer = Customer(
        shop_id=shop.id,
        full_name=customer_data.full_name.strip(),
        phone=customer_data.phone,
        email=str(customer_data.email).lower()
        if customer_data.email else None,
        address=customer_data.address,
    )

    try:
        db.add(customer)
        db.commit()
        db.refresh(customer)
        return customer
    except Exception:
        db.rollback()
        raise


def get_shop_customers(
    db: Session,
    current_user: User,
    shop_id: UUID,
):
    shop = verify_shop_ownership(db, current_user, shop_id)

    if shop is None:
        raise ValueError("Shop not found or access denied.")

    statement = (
        select(Customer)
        .where(Customer.shop_id == shop.id)
        .order_by(Customer.created_at.desc())
    )

    return list(db.scalars(statement).all())


def get_customer_by_id(
    db: Session,
    current_user: User,
    shop_id: UUID,
    customer_id: UUID,
):
    shop = verify_shop_ownership(db, current_user, shop_id)

    if shop is None:
        return None

    return db.scalar(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.shop_id == shop.id,
        )
    )


def update_customer(
    db: Session,
    customer: Customer,
    customer_data: CustomerUpdate,
):
    update_data = customer_data.model_dump(exclude_unset=True)

    if "full_name" in update_data:
        if update_data["full_name"] is None:
            raise ValueError("Customer name cannot be empty.")

        update_data["full_name"] = update_data["full_name"].strip()

    if "email" in update_data and update_data["email"] is not None:
        update_data["email"] = str(update_data["email"]).lower()

    try:
        for field, value in update_data.items():
            setattr(customer, field, value)

        db.commit()
        db.refresh(customer)
        return customer

    except Exception:
        db.rollback()
        raise


def delete_customer(
    db: Session,
    customer: Customer,
):
    existing_order = db.scalar(
        select(Order.id).where(
            Order.customer_id == customer.id
        ).limit(1)
    )

    if existing_order:
        raise ValueError(
            "Customer cannot be deleted because existing orders "
            "are associated with this customer."
        )

    try:
        db.delete(customer)
        db.commit()
        return {"message": "Customer deleted successfully."}

    except Exception:
        db.rollback()
        raise
