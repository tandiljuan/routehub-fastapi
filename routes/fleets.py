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
from libs.tenant.context import CompanyDep, assert_company_match, assert_vehicle_ids_for_company

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
async def fleets_get(db: DbSession, company_id: CompanyDep):
    response = []
    flt_list = db.exec(select(Fleet).where(Fleet.company_id == company_id)).all()
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
    company_id: CompanyDep,
):
    flt_dict = post_data.model_dump(exclude={"vehicles"})
    flt_dict['company_id'] = company_id
    flt_db = Fleet.model_validate(flt_dict)

    db.add(flt_db)
    db.flush()

    vehicle_ids = [
        v.id for v in (post_data.vehicles or [])
        if int(v.qty) > 0
    ]
    assert_vehicle_ids_for_company(db, vehicle_ids, company_id)

    for v in post_data.vehicles or []:
        veh_id = int(v.id)
        veh_qty = int(v.qty)
        if veh_qty < 0:
            continue

        veh_db = db.get(Vehicle, veh_id)
        if veh_db and veh_db.company_id == company_id:
            db.add(FleetVehicle(
                fleet_id=flt_db.id,
                vehicle_id=veh_db.id,
                quantity=veh_qty,
                run_profile=v.to_run_profile(),
            ))

    db.commit()

    flt_url = request.url_for("fleets_id_get", id=flt_db.id)
    response.headers["location"] = f"{flt_url}"

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
async def fleets_id_get(id: int, db: DbSession, company_id: CompanyDep):
    flt_db = db.get(Fleet, id)
    assert_company_match(flt_db, company_id, "Fleet")
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
    company_id: CompanyDep,
):
    flt_db = db.get(Fleet, id)
    assert_company_match(flt_db, company_id, "Fleet")

    flt_dict = patch_data.model_dump(exclude_unset=True, exclude={"vehicles"})
    if flt_dict:
        flt_db.sqlmodel_update(flt_dict)
        db.add(flt_db)

    if patch_data.vehicles is not None:
        vehicle_ids = [
            v.id for v in patch_data.vehicles
            if int(v.qty) > 0
        ]
        assert_vehicle_ids_for_company(db, vehicle_ids, company_id)

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
        if veh_db and veh_db.company_id == company_id:
            db.add(FleetVehicle(
                fleet_id=flt_db.id,
                vehicle_id=veh_db.id,
                quantity=veh_qty,
                run_profile=v.to_run_profile(),
            ))

    db.commit()

    db.refresh(flt_db)
    return flt_db.model_dump()

@router.delete("/{id}", summary="Delete fleet")
async def fleets_id_delete(id: int, db: DbSession, company_id: CompanyDep):
    flt_db = db.get(Fleet, id)
    assert_company_match(flt_db, company_id, "Fleet")
    db.delete(flt_db)
    db.commit()
    return {"code": 200, "message": "Fleet Deleted"}
