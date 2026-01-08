import os
from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    Response,
)
from sqlmodel import select
from models.database import Session as DbSession
from models.delivery import Delivery
from models.delivery_lot import (
    DeliveryLot,
    DeliveryLotCreate,
    DeliveryLotDelivery,
    DeliveryLotDriver,
    DeliveryLotResponse,
    DeliveryLotUpdate,
)
from models.driver import Driver
from libs.optimizer import Optimizer

OPTIMIZER_HOST = os.environ.get("OPTIMIZER_HOST")
OPTIMIZER_PORT = os.environ.get("OPTIMIZER_PORT")
OPTIMIZER_AUTH = os.environ.get("OPTIMIZER_AUTH")

optimizer = None

if OPTIMIZER_HOST and OPTIMIZER_PORT:
    optimizer = Optimizer(
        OPTIMIZER_HOST,
        OPTIMIZER_PORT,
        OPTIMIZER_AUTH,
    )

router = APIRouter(
    prefix="/lots",
    tags=["lots"],
)

@router.get(
    "",
    response_model=list[DeliveryLotResponse],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def delivery_lots_get(db: DbSession):
    response = []
    lot_list = db.exec(select(DeliveryLot)).all()
    for l in lot_list:
        response.append(l.model_dump())
    return response

@router.post(
    "",
    response_model=DeliveryLotResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    status_code=201,
)
async def delivery_lots_post(
    request: Request,
    response: Response,
    db: DbSession,
    post_data: DeliveryLotCreate,
):
    # Add Company ID to submitted data
    lot_dict = post_data.model_dump()
    lot_dict['company_id'] = 1
    lot_dict = DeliveryLot.normalize_submitted_dict(lot_dict)
    lot_db = DeliveryLot.model_validate(lot_dict)

    # Create Lot
    db.add(lot_db)
    db.commit()

    # Create relations between Lot and Deliveries
    post_deliveries = post_data.deliveries or []
    for dlv_id in post_deliveries:
        dlv_id = int(dlv_id)
        dlv_db = db.get(Delivery, dlv_id)
        if dlv_db:
            link = DeliveryLotDelivery(
                lot=lot_db,
                delivery=dlv_db,
            )
            lot_db.deliveries.append(link)
            db.add(lot_db)
            db.commit()

    # Create relations between Lot and Drivers
    post_drivers = post_data.drivers or []
    for drv_id in post_drivers:
        drv_id = int(drv_id)
        drv_db = db.get(Driver, drv_id)
        if drv_db:
            link = DeliveryLotDriver(
                lot=lot_db,
                driver=drv_db,
            )
            lot_db.drivers.append(link)
            db.add(lot_db)
            db.commit()

    # Set location header
    lot_url = request.url_for("delivery_lots_id_get", id=lot_db.id)
    response.headers["location"] = f"{lot_url}"

    # Return (custom serialized) Lot
    db.refresh(lot_db)
    return lot_db.model_dump()

@router.get(
    "/{id}",
    name="delivery_lots_id_get",
    response_model=DeliveryLotResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def delivery_lots_id_get(id: int, db: DbSession):
    lot_db = db.get(DeliveryLot, id)
    if not lot_db:
        raise HTTPException(status_code=404, detail="Delivery lot not found")
    return lot_db.model_dump()

@router.patch(
    "/{id}",
    response_model=DeliveryLotResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def delivery_lots_id_patch(
    id: int,
    db: DbSession,
    patch_data: DeliveryLotUpdate,
):
    lot_db = db.get(DeliveryLot, id)
    if not lot_db:
        raise HTTPException(status_code=404, detail="Delivery lot not found")

    # Update Lot
    lot_dict = patch_data.model_dump(exclude_unset=True)
    lot_dict = DeliveryLot.normalize_submitted_dict(lot_dict)
    lot_db.sqlmodel_update(lot_dict)
    db.add(lot_db)
    db.commit()

    # Update relations between Lot and Deliveries
    post_deliveries = patch_data.deliveries or []
    if len(post_deliveries):
        # Remove existing relation
        for link in lot_db.deliveries:
            db.delete(link)
            db.commit()
        # Load submitted data
        for dlv_id in post_deliveries:
            dlv_id = int(dlv_id)
            dlv_db = db.get(Delivery, dlv_id)
            if dlv_db:
                link = DeliveryLotDelivery(
                    lot=lot_db,
                    delivery=dlv_db,
                )
                lot_db.deliveries.append(link)
                db.add(lot_db)
                db.commit()

    # Update relations between Lot and Drivers
    post_drivers = patch_data.drivers or []
    if len(post_drivers):
        # Remove existing relation
        for link in lot_db.drivers:
            db.delete(link)
            db.commit()
        for drv_id in post_deliveries:
            drv_id = int(drv_id)
            drv_db = db.get(Driver, drv_id)
            if drv_db:
                link = DeliveryLotDriver(
                    lot=lot_db,
                    driver=drv_db,
                )
                lot_db.drivers.append(link)
                db.add(lot_db)
                db.commit()

    # Return (custom serialized) Lot
    db.refresh(lot_db)
    return lot_db.model_dump()

@router.delete("/{id}")
async def delivery_lots_id_delete(
    id: int,
    db: DbSession,
):
    lot_db = db.get(DeliveryLot, id)
    if not lot_db:
        raise HTTPException(status_code=404, detail="Delivery lot not found")
    db.delete(lot_db)
    db.commit()
    return {"code": 200, "message": "Delivery lot Deleted"}

@router.post("/{id}/plan")
async def delivery_lots_id_plan_post(
    id: int,
    db: DbSession,
):
    if not optimizer:
        raise HTTPException(status_code=500)

    lot_db = db.get(DeliveryLot, id)
    if not lot_db:
        raise HTTPException(status_code=404, detail="Delivery lot not found")

    return {"message": "Delivery plan queued for processing"}

@router.get("/{id}/plan")
async def delivery_lots_id_plan_get(id: int):
    return {
        "delivery_lot_id": 1,
        "delivery_paths": [
            {
                "milestone_id": 1,
                "vehicle_id": 1,
                "driver_id": 1,
                "delivery_units": [1,2]
            }
        ]
    }
