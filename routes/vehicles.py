from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    Response,
)
from sqlmodel import select
from models.database import Session as DbSession
from models.vehicle import (
    Vehicle,
    VehicleCreate,
    VehicleResponse,
    VehicleUpdate,
)
from libs.tenant.context import CompanyDep, assert_company_match

router = APIRouter(
    prefix="/vehicles",
    tags=["vehicles"],
)

@router.get(
    "",
    summary="List vehicles",
    response_model=list[VehicleResponse],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
def vehicles_get(db: DbSession, company_id: CompanyDep):
    veh_list = db.exec(select(Vehicle).where(Vehicle.company_id == company_id)).all()
    return veh_list

@router.post(
    "",
    summary="Create vehicle",
    response_model=VehicleResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    status_code=201,
)
def vehicles_post(
    request: Request,
    response: Response,
    db: DbSession,
    post_data: VehicleCreate,
    company_id: CompanyDep,
):
    veh_dict = post_data.model_dump()
    veh_dict['company_id'] = company_id
    veh_db = Vehicle.model_validate(veh_dict)
    db.add(veh_db)
    db.commit()
    db.refresh(veh_db)
    veh_url = request.url_for("vehicles_id_get", id=veh_db.id)
    response.headers["location"] = f"{veh_url}"
    return veh_db

@router.get(
    "/{id}",
    name="vehicles_id_get",
    summary="Get vehicle",
    response_model=VehicleResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
def vehicles_id_get(id: int, db: DbSession, company_id: CompanyDep):
    veh_db = db.get(Vehicle, id)
    assert_company_match(veh_db, company_id, "Vehicle")
    return veh_db

@router.patch(
    "/{id}",
    summary="Update vehicle",
    response_model=VehicleResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
def vehicles_id_patch(id: int, db: DbSession, patch_data: VehicleUpdate, company_id: CompanyDep):
    veh_db = db.get(Vehicle, id)
    assert_company_match(veh_db, company_id, "Vehicle")
    veh_dict = patch_data.model_dump(exclude_unset=True)
    veh_db.sqlmodel_update(veh_dict)
    db.add(veh_db)
    db.commit()
    db.refresh(veh_db)
    return veh_db

@router.delete("/{id}", summary="Delete vehicle")
def vehicles_id_delete(id: int, db: DbSession, company_id: CompanyDep):
    veh_db = db.get(Vehicle, id)
    assert_company_match(veh_db, company_id, "Vehicle")
    db.delete(veh_db)
    db.commit()
    return {"code": 200, "message": "Vehicle Deleted"}
