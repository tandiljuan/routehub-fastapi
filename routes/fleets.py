import re
from fastapi import (
    APIRouter,
    Request,
)
from fastapi.responses import JSONResponse
from models.database import Session as DbSession
from models.vehicle import Vehicle
from models.fleet import (
    Fleet,
    FleetCreate,
    FleetResponse,
    FleetVehicle,
)

router = APIRouter(prefix="/fleets")

@router.get("")
async def fleets_get(request: Request):
    example = ''

    if 'prefer' in request.headers:
        match = re.match(r'example=([\w\.-]+)', request.headers.get("Prefer"))
        if match:
            example = match.group(1)

    if 'empty' == example:
        return []
    elif 'list-1.0' == example:
        return [
            {
                "id": 1,
                "name": "my-fleet",
                "vehicles": [
                    {
                        "vehicle_id": 1,
                        "quantity": 2
                    }
                ]
            }
        ]
    elif 'list-1.1' == example:
        return [
            {
                "id": 1,
                "name": "my-fleet-update",
                "vehicles": [
                    {
                        "vehicle_id": 2,
                        "quantity": 3
                    }
                ]
            }
        ]

    message = {"message": "Work In Progress"}
    return JSONResponse(content=message, status_code=503)

@router.post(
    "",
    response_model=FleetResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def fleets_post(db: DbSession, post_data: FleetCreate):
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

    # Return (custom serialized) Fleet
    db.refresh(flt_db)
    return flt_db.model_dump()

@router.get("/{id}")
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
