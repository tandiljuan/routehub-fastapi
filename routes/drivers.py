from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    Response,
)
from sqlmodel import select
from models.database import Session as DbSession
from models.vehicle import Vehicle
from models.driver import (
    Driver,
    DriverCreate,
    DriverResponse,
    DriverUpdate,
    DriverVehicle,
)

router = APIRouter(
    prefix="/drivers",
    tags=["drivers"],
)

@router.get(
    "",
    summary="List drivers",
    response_model=list[DriverResponse],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def fleets_get(db: DbSession):
    response = []
    drv_list = db.exec(select(Driver)).all()
    for d in drv_list:
        response.append(d.model_dump())
    return response

@router.post(
    "",
    summary="Create driver",
    response_model=DriverResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    status_code=201,
)
async def drivers_post(
    request: Request,
    response: Response,
    db: DbSession,
    post_data: DriverCreate,
):
    # Dump submitted data as dictionary
    drv_dict = post_data.model_dump()
    # Add Company ID to submitted data
    drv_dict['company_id'] = 1
    # Create drivel object from dictionary
    drv_db = Driver.model_validate(drv_dict)

    db.add(drv_db)
    db.flush()

    for v in post_data.vehicles or []:
        veh_id = int(v.id)
        veh_qty = int(v.qty)
        if veh_qty < 1:
            continue

        veh_db = db.get(Vehicle, veh_id)
        if veh_db:
            db.add(DriverVehicle(
                driver_id=drv_db.id,
                vehicle_id=veh_db.id,
                quantity=veh_qty,
            ))

    db.commit()

    # Set location header
    drv_url = request.url_for("drivers_id_get", id=drv_db.id)
    response.headers["location"] = f"{drv_url}"

    # Return (custom serialized) Driver
    db.refresh(drv_db)
    return drv_db.model_dump()

@router.get(
    "/{id}",
    name="drivers_id_get",
    summary="Get driver",
    response_model=DriverResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def drivers_id_get(id: int, db: DbSession):
    drv_db = db.get(Driver, id)
    if not drv_db:
        raise HTTPException(status_code=404, detail="Driver not found")
    return drv_db.model_dump()

@router.patch(
    "/{id}",
    summary="Update driver",
    response_model=DriverResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def drivers_id_patch(
    id: int,
    db: DbSession,
    patch_data: DriverUpdate,
):
    # Retrieve Driver
    drv_db = db.get(Driver, id)
    if not drv_db:
        raise HTTPException(status_code=404, detail="Driver not found")

    # Dump submitted data as dictionary
    drv_dict = patch_data.model_dump(exclude_unset=True)
    # Add Company ID to submitted data
    drv_dict['company_id'] = 1
    # Update drivel object from dictionary
    drv_db.sqlmodel_update(drv_dict)

    db.add(drv_db)

    for v in patch_data.vehicles or []:
        veh_id = int(v.id)
        veh_qty = int(v.qty)
        exist = False

        for link in drv_db.vehicles:
            if link.vehicle_id == veh_id:
                exist = True
                if veh_qty > 0:
                    link.quantity = veh_qty
                    db.add(link)
                else:
                    db.delete(link)
                break

        if exist or veh_qty < 1:
            continue

        veh_db = db.get(Vehicle, veh_id)
        if veh_db:
            db.add(DriverVehicle(
                driver_id=drv_db.id,
                vehicle_id=veh_db.id,
                quantity=veh_qty,
            ))

    db.commit()

    # Return (custom serialized) Driver
    db.refresh(drv_db)
    return drv_db.model_dump()

@router.delete("/{id}", summary="Delete driver")
async def drivers_id_delete(id: int, db: DbSession):
    drv_db = db.get(Driver, id)
    if not drv_db:
        raise HTTPException(status_code=404, detail="Driver not found")
    db.delete(drv_db)
    db.commit()
    return {"code": 200, "message": "Driver Deleted"}
