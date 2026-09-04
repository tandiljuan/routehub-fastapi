from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    Response,
)
from sqlalchemy.orm import selectinload
from sqlmodel import select
from models.database import Session as DbSession
from models.vehicle import Vehicle
from models.fleet import (
    Fleet,
    FleetCreate,
    FleetResponse,
    FleetUpdate,
    FleetVehicle,
    FleetVehicleCreate,
)
from libs.tenant.context import CompanyDep, assert_company_match, assert_vehicle_ids_for_company

router = APIRouter(
    prefix="/fleets",
    tags=["fleets"],
)


def _resolve_alias(v: FleetVehicleCreate, veh_db: Vehicle | None) -> str:
    if v.alias:
        alias = v.alias.strip()
        if not alias:
            raise HTTPException(status_code=422, detail="Fleet vehicle alias cannot be blank")
        return alias
    if veh_db and veh_db.name:
        return veh_db.name
    return str(v.id)


def _assert_unique_aliases(vehicles: list[FleetVehicleCreate], id_to_vehicle: dict[int, Vehicle]) -> list[str]:
    seen: set[str] = set()
    resolved: list[str] = []
    for v in vehicles:
        alias = _resolve_alias(v, id_to_vehicle.get(int(v.id)))
        if alias in seen:
            raise HTTPException(status_code=409, detail=f"Duplicate fleet vehicle alias {alias!r}")
        seen.add(alias)
        resolved.append(alias)
    return resolved


def _load_vehicles_by_id(db: DbSession, vehicle_ids: list[int]) -> dict[int, Vehicle]:
    if not vehicle_ids:
        return {}
    rows = db.exec(select(Vehicle).where(Vehicle.id.in_(vehicle_ids))).all()
    return {int(row.id): row for row in rows}


@router.get(
    "",
    summary="List fleets",
    response_model=list[FleetResponse],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
def fleets_get(db: DbSession, company_id: CompanyDep):
    response = []
    # Serializer walks self.vehicles and reads link.vehicle (run_profile is a
    # JSON column, not a relation). Without both levels eager-loaded this is N+1.
    flt_list = db.exec(
        select(Fleet)
        .options(selectinload(Fleet.vehicles).selectinload(FleetVehicle.vehicle))
        .where(Fleet.company_id == company_id)
    ).all()
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
def fleets_post(
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

    incoming = [v for v in (post_data.vehicles or []) if int(v.qty) >= 0]
    vehicle_ids = [int(v.id) for v in incoming if int(v.qty) > 0]
    assert_vehicle_ids_for_company(db, vehicle_ids, company_id)

    id_to_vehicle = _load_vehicles_by_id(db, [int(v.id) for v in incoming])
    aliases = _assert_unique_aliases(incoming, id_to_vehicle)

    for v, alias in zip(incoming, aliases):
        veh_db = id_to_vehicle.get(int(v.id))
        if veh_db and veh_db.company_id == company_id:
            db.add(FleetVehicle(
                fleet_id=flt_db.id,
                vehicle_id=veh_db.id,
                alias=alias,
                quantity=int(v.qty),
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
def fleets_id_get(id: int, db: DbSession, company_id: CompanyDep):
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
def fleets_id_patch(
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
        incoming = [v for v in patch_data.vehicles if int(v.qty) >= 0]
        vehicle_ids = [int(v.id) for v in incoming if int(v.qty) > 0]
        assert_vehicle_ids_for_company(db, vehicle_ids, company_id)

        id_to_vehicle = _load_vehicles_by_id(db, [int(v.id) for v in incoming])
        aliases = _assert_unique_aliases(incoming, id_to_vehicle)

        existing_by_alias = {link.alias: link for link in flt_db.vehicles}

        for v, alias in zip(incoming, aliases):
            veh_id = int(v.id)
            existing = existing_by_alias.get(alias)
            if existing is not None:
                if existing.vehicle_id != veh_id:
                    raise HTTPException(status_code=409, detail=f"Alias {alias!r} bound to vehicle {existing.vehicle_id}")
                existing.quantity = int(v.qty)
                existing.run_profile = v.to_run_profile()
                db.add(existing)
                continue

            veh_db = id_to_vehicle.get(veh_id)
            if veh_db and veh_db.company_id == company_id:
                db.add(FleetVehicle(
                    fleet_id=flt_db.id,
                    vehicle_id=veh_db.id,
                    alias=alias,
                    quantity=int(v.qty),
                    run_profile=v.to_run_profile(),
                ))

        # `vehicles` llega siempre completo desde el editor, así que un link que
        # no viene en el payload fue borrado por el usuario. Sin esto el PATCH
        # solo hacía upsert y los vehículos eliminados reaparecían al recargar.
        keep_aliases = set(aliases)
        for link in list(flt_db.vehicles):
            if link.alias not in keep_aliases:
                db.delete(link)

    db.commit()

    db.refresh(flt_db)
    return flt_db.model_dump()

@router.delete("/{id}", summary="Delete fleet")
def fleets_id_delete(id: int, db: DbSession, company_id: CompanyDep):
    flt_db = db.get(Fleet, id)
    assert_company_match(flt_db, company_id, "Fleet")
    db.delete(flt_db)
    db.commit()
    return {"code": 200, "message": "Fleet Deleted"}
