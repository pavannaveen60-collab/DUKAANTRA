from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.dependencies import get_current_user
from database import get_db
from models.user import User
from services.ai_workforce_service import (
    AnalysisAlreadyRunning,
    AnalysisExecutionError,
    get_ai_workforce_status,
    run_ai_workforce,
)


router = APIRouter(
    prefix="/shops/{shop_id}/ai-workforce",
    tags=["AI Workforce"],
)


@router.get("/")
def read_ai_workforce(
    shop_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return get_ai_workforce_status(db, current_user, shop_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error


@router.get("/history")
def read_ai_workforce_history(
    shop_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return get_ai_workforce_status(db, current_user, shop_id)["history"]
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error


@router.post("/run", status_code=status.HTTP_200_OK)
def execute_ai_workforce(
    shop_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return run_ai_workforce(db, current_user, shop_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except AnalysisAlreadyRunning as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except AnalysisExecutionError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        ) from error
