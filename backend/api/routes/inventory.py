
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.user import User

from schemas.inventory import (
    InventoryCreate,
    InventoryUpdate,
    InventoryResponse,
    StockAdjustment,
)
from schemas.inventory_movement import InventoryMovementResponse

from services.inventory_service import (
    create_inventory,
    get_shop_inventory,
    get_inventory_by_id,
    update_inventory,
    adjust_stock,
    get_low_stock_inventory,
)

from services.inventory_movement_service import get_inventory_movements

from core.dependencies import get_current_user


router = APIRouter(
    prefix="/shops/{shop_id}/inventory",
    tags=["Inventory"],
)


@router.post("/", response_model=InventoryResponse, status_code=status.HTTP_201_CREATED)
def add_inventory(
    shop_id: UUID,
    inventory_data: InventoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return create_inventory(db, current_user, shop_id, inventory_data)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.get("/", response_model=list[InventoryResponse])
def list_inventory(
    shop_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return get_shop_inventory(db, current_user, shop_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.get("/low-stock", response_model=list[InventoryResponse])
def list_low_stock(
    shop_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return get_low_stock_inventory(db, current_user, shop_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.get(
    "/{inventory_id}/movements",
    response_model=list[InventoryMovementResponse],
)
def list_inventory_movements(
    shop_id: UUID,
    inventory_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return get_inventory_movements(
            db, current_user, shop_id, inventory_id
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.get("/{inventory_id}", response_model=InventoryResponse)
def retrieve_inventory(
    shop_id: UUID,
    inventory_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inventory = get_inventory_by_id(
        db, current_user, shop_id, inventory_id
    )

    if inventory is None:
        raise HTTPException(status_code=404, detail="Inventory record not found.")

    return inventory


@router.patch("/{inventory_id}", response_model=InventoryResponse)
def edit_inventory(
    shop_id: UUID,
    inventory_id: UUID,
    inventory_data: InventoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inventory = get_inventory_by_id(
        db, current_user, shop_id, inventory_id
    )

    if inventory is None:
        raise HTTPException(status_code=404, detail="Inventory record not found.")

    try:
        return update_inventory(
            db, inventory, inventory_data, current_user
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.post("/{inventory_id}/adjust", response_model=InventoryResponse)
def change_stock(
    shop_id: UUID,
    inventory_id: UUID,
    adjustment: StockAdjustment,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inventory = get_inventory_by_id(
        db, current_user, shop_id, inventory_id
    )

    if inventory is None:
        raise HTTPException(status_code=404, detail="Inventory record not found.")

    try:
        return adjust_stock(
            db, inventory, adjustment, current_user
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
