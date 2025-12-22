from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    Response,
)
from sqlmodel import select
from models.database import Session as DbSession
from models.vehicle import Vehicle
from models.fleet import (
    Fleet,
    FleetCreate,
    FleetResponse,
    FleetUpdate,
    FleetVehicle,
)

router = APIRouter(prefix="/fleets")

@router.get(
    "",
    response_model=list[FleetResponse],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def fleets_get(db: DbSession):
    response = []
    flt_list = db.exec(select(Fleet)).all()
    for f in flt_list:
        response.append(f.model_dump())
    return response

@router.post(
    "",
    response_model=FleetResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    status_code=201,
)
async def fleets_post(
    request: Request,
    response: Response,
    db: DbSession,
    post_data: FleetCreate,
):
    # Add Company ID to submitted data
    flt_dict = post_data.model_dump()
    flt_dict['company_id'] = 1
    flt_db = Fleet.model_validate(flt_dict)

    # Create Fleet
    db.add(flt_db)
    db.commit()

    # Create relations between Fleet and Vehicles
    post_vehicles = post_data.vehicles or []
    for v in post_data.vehicles:
        veh_id = int(v.id)
        veh_qty = int(v.qty)

        if veh_qty < 1:
            continue

        veh_db = db.get(Vehicle, veh_id)
        if veh_db:
            link = FleetVehicle(
                fleet=flt_db,
                vehicle=veh_db,
                quantity=veh_qty,
            )
            flt_db.vehicles.append(link)
            db.add(flt_db)
            db.commit()

    # Set location header
    flt_url = request.url_for("fleets_id_get", id=flt_db.id)
    response.headers["location"] = f"{flt_url}"

    # Return (custom serialized) Fleet
    db.refresh(flt_db)
    return flt_db.model_dump()

@router.get(
    "/{id}",
    name="fleets_id_get",
    response_model=FleetResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def fleets_id_get(id: int, db: DbSession):
    flt_db = db.get(Fleet, id)
    if not flt_db:
        raise HTTPException(status_code=404, detail="Fleet not found")
    return flt_db.model_dump()

@router.patch(
    "/{id}",
    response_model=FleetResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def fleets_id_patch(
    id: int,
    db: DbSession,
    patch_data: FleetUpdate,
):
    # Retrieve Fleet
    flt_db = db.get(Fleet, id)
    if not flt_db:
        raise HTTPException(status_code=404, detail="Fleet not found")

    # Update Fleet
    flt_dict = patch_data.model_dump(exclude_unset=True)
    flt_db.sqlmodel_update(flt_dict)
    db.add(flt_db)
    db.commit()

    # Update relations between Fleet and Vehicles
    patch_vehicles = patch_data.vehicles or []
    for v in patch_vehicles:
        veh_id = int(v.id)
        veh_qty = int(v.qty)
        exist = False

        # Update existing relation
        for link in flt_db.vehicles:
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
            link = FleetVehicle(
                fleet=flt_db,
                vehicle=veh_db,
                quantity=veh_qty,
            )
            flt_db.vehicles.append(link)
            db.add(flt_db)
            db.commit()

    # Return (custom serialized) Fleet
    db.refresh(flt_db)
    return flt_db.model_dump()

@router.delete("/{id}")
async def fleets_id_delete(id: int, db: DbSession):
    flt_db = db.get(Fleet, id)
    if not flt_db:
        raise HTTPException(status_code=404, detail="Fleet not found")
    db.delete(flt_db)
    db.commit()
    return {"code": 200, "message": "Fleet Deleted"}
