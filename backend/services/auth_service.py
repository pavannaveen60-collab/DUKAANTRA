
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.user import User
from schemas.auth import UserRegister, UserLogin
from core.security import (
    hash_password,
    verify_password,
    create_access_token,
)


def register_user(db: Session, user_data: UserRegister):
    """Register a new merchant account."""

    email = str(user_data.email).strip().lower()
    existing_user = db.scalar(
        select(User).where(func.lower(User.email) == email)
    )

    if existing_user:
        raise ValueError("An account with this email already exists.")

    user = User(
        full_name=user_data.full_name,
        email=email,
        password_hash=hash_password(user_data.password),
        phone=user_data.phone,
    )

    db.add(user)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise ValueError(
            "An account with this email already exists."
        ) from error

    db.refresh(user)

    return user


def authenticate_user(
    db: Session,
    login_data: UserLogin
):
    """Verify merchant login credentials."""

    email = str(login_data.email).strip().lower()

    user = db.scalar(
        select(User).where(User.email == email)
    )

    if not user:
        return None

    if not verify_password(
        login_data.password,
        user.password_hash
    ):
        return None

    return user


def create_user_token(user: User) -> str:
    """Generate an access token for an authenticated merchant."""

    return create_access_token(subject=str(user.id))
