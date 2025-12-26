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

    # Save new Driver in the database
    db.add(drv_db)
    db.commit()

    # Create relations between Driver and Vehicles
    post_vehicles = post_data.vehicles or []
    for v in post_vehicles:
        veh_id = int(v.id)
        veh_qty = int(v.qty)

        if veh_qty < 1:
            continue

        veh_db = db.get(Vehicle, veh_id)
        if veh_db:
            link = DriverVehicle(
                fleet=drv_db,
                vehicle=veh_db,
                quantity=veh_qty,
            )
            drv_db.vehicles.append(link)
            db.add(drv_db)
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
    db.commit()

    # Update relations between Driver and Vehicles
    patch_vehicles = patch_data.vehicles or []
    for v in patch_vehicles:
        veh_id = int(v.id)
        veh_qty = int(v.qty)
        exist = False

        # Update existing relation
        for link in drv_db.vehicles:
            if link.vehicle_id == veh_id:
                exist = True
                if veh_qty != link.quantity:
                    if veh_qty > 0:
                        link.quantity = veh_qty
                        db.add(link)
                        db.commit()
                    else:
                        db.delete(link)
                        db.commit()
                break

        if exist or veh_qty < 1:
            continue

        # Create new relation
        veh_db = db.get(Vehicle, veh_id)
        if veh_db:
            link = DriverVehicle(
                fleet=drv_db,
                vehicle=veh_db,
                quantity=veh_qty,
            )
            drv_db.vehicles.append(link)
            db.add(drv_db)
            db.commit()

    # Return (custom serialized) Driver
    db.refresh(drv_db)
    return drv_db.model_dump()

@router.delete("/{id}")
async def drivers_id_delete(id: int, db: DbSession):
    drv_db = db.get(Driver, id)
    if not drv_db:
        raise HTTPException(status_code=404, detail="Driver not found")
    db.delete(drv_db)
    db.commit()
    return {"code": 200, "message": "Driver Deleted"}
