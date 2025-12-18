import re
from fastapi import (
    APIRouter,
    Request,
)
from fastapi.responses import JSONResponse
from sqlmodel import select
from models.database import Session as DbSession
from models.vehicle import (
    Vehicle,
    VehicleCreate,
    VehicleResponse,
)

router = APIRouter(prefix="/vehicles")

@router.get(
    "",
    response_model=list[VehicleResponse],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def vehicles_get(db: DbSession):
    veh_list = db.exec(select(Vehicle)).all()
    return veh_list

@router.post(
    "",
    response_model=VehicleResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def vehicles_post(db: DbSession, post_data: VehicleCreate):
    veh_dict = post_data.model_dump()
    veh_dict['company_id'] = 1
    veh_db = Vehicle.model_validate(veh_dict)
    db.add(veh_db)
    db.commit()
    db.refresh(veh_db)
    return veh_db

@router.get("/{id}")
async def vehicles_id_get(id: int, request: Request):
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

    if 'vehicle-1.0' == example:
        return {
            "id": 1,
            "name": "pickup",
            "volume": 1230000,
            "volume_unit": "CUBIC_CENTIMETER",
            "consumption": 12,
            "consumption_unit": "LITERS_PER_100KM",
            "category_type": "PICKUP",
            "engine_type": "DIESEL"
        }
    elif 'vehicle-1.1' == example:
        return {
            "id": 1,
            "name": "pickup-update",
            "volume": 1230000,
            "volume_unit": "CUBIC_CENTIMETER",
            "consumption": 10,
            "consumption_unit": "LITERS_PER_100KM",
            "category_type": "PICKUP",
            "engine_type": "DIESEL"
        }

    message = {"message": "Work In Progress"}
    return JSONResponse(content=message, status_code=503)

@router.patch("/{id}")
async def vehicles_id_patch(id: int):
    return {
        "id": 1,
        "name": "pickup-update",
        "volume": 1230000,
        "volume_unit": "CUBIC_CENTIMETER",
        "consumption": 10,
        "consumption_unit": "LITERS_PER_100KM",
        "category_type": "PICKUP",
        "engine_type": "DIESEL"
    }

@router.delete("/{id}")
async def vehicles_id_delete(id: int):
    return {"message": "Vehicle Deleted"}
