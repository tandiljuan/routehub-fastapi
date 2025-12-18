from fastapi import (
    APIRouter,
    HTTPException,
)
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

@router.get(
    "/{id}",
    response_model=VehicleResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def vehicles_id_get(id: int, db: DbSession):
    veh_db = db.get(Vehicle, id)
    if not veh_db:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return veh_db

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
