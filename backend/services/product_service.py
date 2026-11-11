from uuid import UUID
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.product import Product
from models.shop import Shop
from models.user import User
from schemas.product import ProductCreate, ProductUpdate


def verify_shop_ownership(
    db: Session,
    current_user: User,
    shop_id: UUID
) -> Shop | None:
    """Verify that the shop belongs to the authenticated merchant."""

    statement = select(Shop).where(
        Shop.id == shop_id,
        Shop.owner_id == current_user.id
    )

    return db.scalar(statement)


def create_product(
    db: Session,
    current_user: User,
    shop_id: UUID,
    product_data: ProductCreate
) -> Product:
    """Create a product inside a merchant-owned shop."""

    shop = verify_shop_ownership(db, current_user, shop_id)

    if shop is None:
        raise ValueError("Shop not found or access denied.")

    product = Product(
        shop_id=shop.id,
        name=product_data.name.strip(),
        sku=product_data.sku.strip() if product_data.sku else None,
        category=product_data.category,
        description=product_data.description,
        price=product_data.price,
        cost_price=product_data.cost_price,
    )

    db.add(product)
    db.commit()
    db.refresh(product)

    return product


def get_shop_products(
    db: Session,
    current_user: User,
    shop_id: UUID,
    include_inactive: bool = False
) -> list[Product]:
    """List products belonging to a merchant-owned shop."""

    shop = verify_shop_ownership(db, current_user, shop_id)

    if shop is None:
        raise ValueError("Shop not found or access denied.")

    statement = select(Product).where(
        Product.shop_id == shop.id
    )

    if not include_inactive:
        statement = statement.where(Product.is_active.is_(True))

    statement = statement.order_by(Product.created_at.desc())

    return list(db.scalars(statement).all())


def get_product_by_id(
    db: Session,
    current_user: User,
    shop_id: UUID,
    product_id: UUID
) -> Product | None:
    """Find a product only inside a merchant-owned shop."""

    shop = verify_shop_ownership(db, current_user, shop_id)

    if shop is None:
        return None

    statement = select(Product).where(
        Product.id == product_id,
        Product.shop_id == shop.id
    )

    return db.scalar(statement)


def update_product(
    db: Session,
    product: Product,
    product_data: ProductUpdate
) -> Product:
    """Update supplied product fields."""

    update_data = product_data.model_dump(exclude_unset=True)

    if "name" in update_data:
        if update_data["name"] is None:
            raise ValueError("Product name cannot be empty.")

        update_data["name"] = update_data["name"].strip()

    if "sku" in update_data and update_data["sku"] is not None:
        update_data["sku"] = update_data["sku"].strip() or None

    for field, value in update_data.items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)

    return product