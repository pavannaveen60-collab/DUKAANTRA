
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.shop import Shop
from models.user import User
from schemas.shop import ShopCreate, ShopUpdate


def create_shop(
    db: Session,
    current_user: User,
    shop_data: ShopCreate
) -> Shop:
    """Create a shop owned by the authenticated merchant."""

    shop = Shop(
        owner_id=current_user.id,
        shop_name=shop_data.shop_name.strip(),
        business_type=shop_data.business_type,
        phone=shop_data.phone,
        address=shop_data.address,
        city=shop_data.city,
        state=shop_data.state,
        pincode=shop_data.pincode,
    )

    db.add(shop)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(shop)

    return shop


def get_my_shops(
    db: Session,
    current_user: User
) -> list[Shop]:
    """Return only shops belonging to the authenticated merchant."""

    statement = (
        select(Shop)
        .where(Shop.owner_id == current_user.id)
        .order_by(Shop.created_at.desc())
    )

    return list(db.scalars(statement).all())


def get_shop_by_id(
    db: Session,
    current_user: User,
    shop_id: UUID
) -> Shop | None:
    """Find a shop only if it belongs to the authenticated merchant."""

    statement = select(Shop).where(
        Shop.id == shop_id,
        Shop.owner_id == current_user.id
    )

    return db.scalar(statement)


def update_shop(
    db: Session,
    shop: Shop,
    shop_data: ShopUpdate
) -> Shop:
    """Update only the fields supplied by the merchant."""

    update_data = shop_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if field == "shop_name" and value is not None:
            value = value.strip()

        setattr(shop, field, value)

    db.commit()
    db.refresh(shop)

    return shop
