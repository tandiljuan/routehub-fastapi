import re
from fastapi import (
    APIRouter,
    Request,
    Response,
)
from fastapi.responses import JSONResponse
from models.database import Session as DbSession
from models.delivery import Delivery
from models.delivery_lot import (
    DeliveryLot,
    DeliveryLotCreate,
    DeliveryLotDelivery,
    DeliveryLotDriver,
    DeliveryLotResponse,
)
from models.driver import Driver

router = APIRouter(prefix="/lots")

@router.get("")
async def delivery_lots_get(request: Request):
    example = ''

    if 'prefer' in request.headers:
        match = re.match(r'example=([\w\.-]+)', request.headers.get("Prefer"))
        if match:
            example = match.group(1)

    if 'empty' == example:
        return []
    elif 'list-1.0' == example:
        return [
            {
                "id": 1,
                "milestone_id": 1,
                "deliveries": [1],
                "fleet_id": 1,
                "drivers": [1],
                "state": "UNPROCESSED"
            }
        ]
    elif 'list-1.1' == example:
        return [
            {
                "id": 1,
                "milestone_id": 1,
                "deliveries": [1,2],
                "fleet_id": 1,
                "drivers": [1],
                "state": "UNPROCESSED"
            }
        ]

    message = {"message": "Work In Progress"}
    return JSONResponse(content=message, status_code=503)

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
)
async def delivery_lots_id_get(id: int, request: Request):
    key = ''
    example = ''

    if 'prefer' in request.headers:
        match = re.match(r'(\w+)=([\w\.-]+)', request.headers.get("Prefer"))
        if match:
            key = match.group(1)
            example = match.group(2)

    if 'code' == key:
        message = {"message": "..."}
        return JSONResponse(content=message, status_code=int(example))

    if 'delivery-lot-1.0' == example:
        return {
            "id": 1,
            "milestone_id": 1,
            "deliveries": [1],
            "fleet_id": 1,
            "drivers": [1],
            "state": "UNPROCESSED"
        }
    elif 'delivery-lot-1.1' == example:
        return {
            "id": 1,
            "milestone_id": 1,
            "deliveries": [1,2],
            "fleet_id": 1,
            "drivers": [1],
            "state": "UNPROCESSED"
        }

    message = {"message": "Work In Progress"}
    return JSONResponse(content=message, status_code=503)

@router.patch("/{id}")
async def delivery_lots_id_patch(id: int):
    return {
        "id": 1,
        "milestone_id": 1,
        "deliveries": [1,2],
        "fleet_id": 1,
        "drivers": [1],
        "state": "UNPROCESSED"
    }

@router.delete("/{id}")
async def delivery_lots_id_delete(id: int):
    return {"message": "Delivery Lot Deleted"}

@router.post("/{id}/plan")
async def delivery_lots_id_plan_post(id: int):
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
