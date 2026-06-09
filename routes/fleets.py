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

router = APIRouter(
    prefix="/fleets",
    tags=["fleets"],
)

@router.get(
    "",
    summary="List fleets",
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
    summary="Create fleet",
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

    db.add(flt_db)
    db.flush()

    for v in post_data.vehicles or []:
        veh_id = int(v.id)
        veh_qty = int(v.qty)
        if veh_qty < 0:
            continue

        veh_db = db.get(Vehicle, veh_id)
        if veh_db:
            db.add(FleetVehicle(
                fleet_id=flt_db.id,
                vehicle_id=veh_db.id,
                quantity=veh_qty,
                run_profile=v.to_run_profile(),
            ))

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
    summary="Get fleet",
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
    summary="Update fleet",
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

    flt_dict = patch_data.model_dump(exclude_unset=True)
    flt_db.sqlmodel_update(flt_dict)
    db.add(flt_db)

    for v in patch_data.vehicles or []:
        veh_id = int(v.id)
        veh_qty = int(v.qty)
        if veh_qty < 0:
            continue

        exist = False
        for link in flt_db.vehicles:
            if link.vehicle_id == veh_id:
                exist = True
                link.quantity = veh_qty
                link.run_profile = v.to_run_profile()
                db.add(link)
                break

        if exist:
            continue

        veh_db = db.get(Vehicle, veh_id)
        if veh_db:
            db.add(FleetVehicle(
                fleet_id=flt_db.id,
                vehicle_id=veh_db.id,
                quantity=veh_qty,
                run_profile=v.to_run_profile(),
            ))

    db.commit()

    # Return (custom serialized) Fleet
    db.refresh(flt_db)
    return flt_db.model_dump()

@router.delete("/{id}", summary="Delete fleet")
async def fleets_id_delete(id: int, db: DbSession):
    flt_db = db.get(Fleet, id)
    if not flt_db:
        raise HTTPException(status_code=404, detail="Fleet not found")
    db.delete(flt_db)
    db.commit()
    return {"code": 200, "message": "Fleet Deleted"}
