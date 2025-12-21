import re
from fastapi import (
    APIRouter,
    Request,
    Response,
)
from fastapi.responses import JSONResponse
from sqlmodel import select
from models.database import Session as DbSession
from models.vehicle import Vehicle
from models.fleet import (
    Fleet,
    FleetCreate,
    FleetResponse,
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
)
async def fleets_id_get(id: int, request: Request):
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

    if 'fleet-1.0' == example:
        return {
            "id": 1,
            "name": "my-fleet",
            "vehicles": [
                {
                    "vehicle_id": 1,
                    "quantity": 2
                }
            ]
        }
    elif 'fleet-1.1' == example:
        return {
            "id": 1,
            "name": "my-fleet-update",
            "vehicles": [
                {
                    "vehicle_id": 2,
                    "quantity": 3
                }
            ]
        }

    message = {"message": "Work In Progress"}
    return JSONResponse(content=message, status_code=503)

@router.patch("/{id}")
async def fleets_id_patch(id: int):
    return {
        "id": 1,
        "name": "my-fleet-update",
        "vehicles": [
            {
                "vehicle_id": 2,
                "quantity": 3
            }
        ]
    }

@router.delete("/{id}")
async def fleets_id_delete(id: int):
    return {"message": "Fleet Deleted"}
