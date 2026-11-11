
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from core.dependencies import get_current_user
from models.user import User

from services.ml_integration_service import (
    get_demand_and_stockout_predictions,
    get_sales_forecast,
    get_sales_anomaly_report,
)

router = APIRouter(
    prefix="/shops/{shop_id}/ml",
    tags=["Machine Learning"],
)


@router.get("/demand")
def demand_predictions(
    shop_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return get_demand_and_stockout_predictions(
            db, current_user, shop_id
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except FileNotFoundError as error:
        raise HTTPException(status_code=503, detail=str(error))


@router.get("/sales-forecast")
def sales_forecast(
    shop_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return get_sales_forecast(
            db, current_user, shop_id
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except FileNotFoundError as error:
        raise HTTPException(status_code=503, detail=str(error))


@router.get("/anomalies")
def sales_anomalies(
    shop_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return get_sales_anomaly_report(
            db, current_user, shop_id
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except FileNotFoundError as error:
        raise HTTPException(status_code=503, detail=str(error))
