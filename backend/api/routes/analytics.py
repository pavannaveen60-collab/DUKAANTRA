
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from core.dependencies import get_current_user
from models.user import User
from services.analytics_service import (
    get_sales_overview,
    get_daily_sales,
    get_monthly_sales,
    get_top_selling_products,
)

router = APIRouter(
    prefix="/shops/{shop_id}/analytics",
    tags=["Sales Analytics"],
)


@router.get("/overview")
def sales_overview(
    shop_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return get_sales_overview(db, current_user, shop_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.get("/daily")
def daily_sales(
    shop_id: UUID,
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return get_daily_sales(db, current_user, shop_id, days)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.get("/monthly")
def monthly_sales(
    shop_id: UUID,
    months: int = Query(default=6, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return get_monthly_sales(db, current_user, shop_id, months)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.get("/top-products")
def top_products(
    shop_id: UUID,
    limit: int = Query(default=5, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return get_top_selling_products(
            db, current_user, shop_id, limit
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))
